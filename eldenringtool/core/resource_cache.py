from __future__ import annotations

import hashlib
import json
import math
import os
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

SCHEMA = 3
SCANNER_VERSION = "0.1.0"
REQUIRED_GAME_FILES = ("eldenring.exe", "regulation.bin")
ARCHIVE_INDEX_FILES = (
    "Data0.bhd", "Data1.bhd", "Data2.bhd", "Data3.bhd", "DLC.bhd",
    *(f"DLC{i:02d}.bhd" for i in range(1, 10)),
)
ARCHIVE_DATA_FILES = tuple(name[:-4] + ".bdt" for name in ARCHIVE_INDEX_FILES)
REQUIRED_OUTPUTS = (
    "assets/tiles/manifest.json",
    "data/markers.json",
    "data/items.json",
    "data/unique_drops.json",
    "data/mausoleums.json",
    "data/catalog.json",
    "data/legacy-conv.json",
)


def required_outputs(mod_dir: Path | None = None) -> tuple[str, ...]:
    # A selected mod always gets a pieces file. For non-Reforged mods the
    # extractor deliberately emits an empty, valid corpus rather than phantom
    # Reforged markers.
    if mod_dir:
        return (*REQUIRED_OUTPUTS, "data/pieces.json")
    return REQUIRED_OUTPUTS


GENERATED_OUTPUTS = (
    "assets/tiles",
    "assets/icons/items",
    "cache",
    "data/markers.json",
    "data/items.json",
    "data/unique_drops.json",
    "data/catalog.json",
    "data/mausoleums.json",
    "data/pieces.json",
    "data/legacy-conv.json",
    "data/map-icons.json",
    "data/surface-height-report.json",
)
SCAN_BACKUP_DIR = ".eldenringtool-scan-backup"
SCAN_BACKUP_COMPLETE = ".backup-complete"


@dataclass(frozen=True)
class CacheStatus:
    valid: bool
    reason: str
    game_dir: str = ""
    metadata_refreshed: bool = False


def _sha256(path: Path, block: int = 4 * 1024 * 1024) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(block), b""):
            h.update(chunk)
    return h.hexdigest()


def normalize_game_dir(selected: str | os.PathLike[str]) -> Path:
    """Accept eldenring.exe, Game/, or the ELDEN RING parent directory."""
    p = Path(selected).expanduser()
    if p.is_file():
        if p.name.lower() != "eldenring.exe":
            raise ValueError("请选择 eldenring.exe")
        p = p.parent
    candidates = [p, p / "Game"]
    for c in candidates:
        if all((c / name).is_file() for name in REQUIRED_GAME_FILES):
            return c.resolve()
    raise ValueError("所选位置不是有效的 Elden Ring Game 目录：缺少 eldenring.exe 或 regulation.bin")


def fingerprint(path: Path) -> dict[str, Any]:
    st = path.stat()
    return {"size": st.st_size, "mtime_ns": st.st_mtime_ns, "sha256": _sha256(path)}


def metadata_fingerprint(path: Path) -> dict[str, Any]:
    st = path.stat()
    return {"size": st.st_size, "mtime_ns": st.st_mtime_ns}


def archive_index_signatures(game_dir: Path) -> dict[str, dict[str, Any]]:
    """Strong fingerprints for BHD archive indexes present in this install.

    On later startups hashes are recomputed only if size/mtime changed, so this
    is cheap in the common path but still distinguishes same-size patches.
    """
    return {
        name: fingerprint(game_dir / name)
        for name in ARCHIVE_INDEX_FILES
        if (game_dir / name).is_file()
    }


def archive_data_metadata(game_dir: Path) -> dict[str, dict[str, Any]]:
    """Cheap signatures for the multi-GB BDT archive payloads.

    Full hashing would make every startup scan many gigabytes. Size + nanosecond
    mtime catches normal Steam patch/replacement events, while the paired BHD
    index still receives a full SHA-256 fingerprint.
    """
    return {
        name: metadata_fingerprint(game_dir / name)
        for name in ARCHIVE_DATA_FILES
        if (game_dir / name).is_file()
    }


def mod_loose_signature(mod_dir: Path) -> dict[str, Any]:
    """Deterministic metadata signature for loose DCX resources used by parsers.

    ``regulation.bin`` has its own full SHA-256. Loose parser overrides are DCX
    files (MSB, EMEVD, FMG/message binders and menu assets), so path+size+mtime
    catches normal mod-manager swaps without hashing a potentially huge mod tree
    at every startup.
    """
    root = Path(mod_dir)
    entries: list[tuple[str, int, int]] = []
    for base, dirs, files in os.walk(root, followlinks=False):
        dirs[:] = [d for d in dirs if not (Path(base) / d).is_symlink()]
        for name in files:
            if not name.lower().endswith(".dcx"):
                continue
            p = Path(base) / name
            try:
                st = p.stat()
            except OSError:
                continue
            rel = p.relative_to(root).as_posix().lower()
            entries.append((rel, st.st_size, st.st_mtime_ns))
    entries.sort()
    h = hashlib.sha256()
    total = 0
    for rel, size, mtime_ns in entries:
        total += size
        h.update(rel.encode("utf-8", "surrogatepass"))
        h.update(b"\0")
        h.update(str(size).encode("ascii"))
        h.update(b"\0")
        h.update(str(mtime_ns).encode("ascii"))
        h.update(b"\n")
    return {"count": len(entries), "total_size": total, "metadata_sha256": h.hexdigest()}


def content_signature(paths: dict[str, Path]) -> dict[str, dict[str, Any]]:
    return {name: fingerprint(path) for name, path in paths.items()}


def same_content_signature(a: dict[str, Any], b: dict[str, Any]) -> bool:
    return a.get("size") == b.get("size") and a.get("sha256") == b.get("sha256")


def _tile_integrity(root: Path) -> tuple[bool, str, int]:
    manifest = root / "assets" / "tiles" / "manifest.json"
    try:
        doc = json.loads(manifest.read_text(encoding="utf-8"))
    except Exception as exc:
        return False, f"地图瓦片索引无效：{exc}", 0
    fmt = str(doc.get("format") or "webp").lower()
    if fmt not in ("webp", "png"):
        return False, f"地图瓦片格式无效：{fmt}", 0
    masters = doc.get("masters")
    if not isinstance(masters, dict) or not masters:
        return False, "地图瓦片索引为空", 0

    total = 0
    for master, info in masters.items():
        if not isinstance(info, dict):
            return False, f"地图瓦片索引损坏：{master}", total
        levels = info.get("tiles")
        if not isinstance(levels, dict) or not levels:
            return False, f"地图瓦片索引缺少层级：{master}", total
        master_total = 0
        for level, coords in levels.items():
            try:
                level_num = int(level)
            except (TypeError, ValueError):
                return False, f"地图瓦片层级无效：{master}/{level}", total
            if level_num < 0 or not isinstance(coords, list):
                return False, f"地图瓦片索引损坏：{master}/{level}", total
            seen: set[tuple[int, int]] = set()
            for xy in coords:
                if (
                    not isinstance(xy, list) or len(xy) != 2
                    or not all(isinstance(v, int) and not isinstance(v, bool) and v >= 0 for v in xy)
                ):
                    return False, f"地图瓦片索引坐标损坏：{master}/{level}", total
                x, y = xy
                if (x, y) in seen:
                    return False, f"地图瓦片索引坐标重复：{master}/{level}/{x}/{y}", total
                seen.add((x, y))
                p = root / "assets" / "tiles" / str(master) / str(level) / str(x) / f"{y}.{fmt}"
                if not p.is_file():
                    return False, f"地图瓦片缺失：{master}/{level}/{x}/{y}.{fmt}", total
                try:
                    if p.stat().st_size <= 0:
                        return False, f"地图瓦片为空：{master}/{level}/{x}/{y}.{fmt}", total
                except OSError as exc:
                    return False, f"地图瓦片无法读取：{master}/{level}/{x}/{y}.{fmt}: {exc}", total
                total += 1
                master_total += 1
        if master_total <= 0:
            return False, f"地图瓦片主图为空：{master}", total
    if total <= 0:
        return False, "地图瓦片为空", 0
    return True, "", total


def build_manifest(
    root: Path,
    game_dir: Path,
    mod_dir: Path | None = None,
    game_files: dict[str, Any] | None = None,
) -> dict[str, Any]:
    game_dir = normalize_game_dir(game_dir)
    files = game_files or {name: fingerprint(game_dir / name) for name in REQUIRED_GAME_FILES}
    ok, reason, tile_count = _tile_integrity(root)
    if not ok:
        raise RuntimeError(reason)
    outputs = required_outputs(mod_dir)
    output_files = {rel: fingerprint(root / rel) for rel in outputs}
    out: dict[str, Any] = {
        "schema": SCHEMA,
        "scanner_version": SCANNER_VERSION,
        "game_dir": str(game_dir),
        "files": files,
        "archive_indexes": archive_index_signatures(game_dir),
        "archive_data": archive_data_metadata(game_dir),
        "outputs": list(outputs),
        "output_files": output_files,
        "tile_count": tile_count,
    }
    if mod_dir:
        resolved_mod = Path(mod_dir).resolve()
        r = resolved_mod / "regulation.bin"
        if r.is_file():
            out["mod_dir"] = str(resolved_mod)
            out["mod_regulation"] = fingerprint(r)
            out["mod_loose"] = mod_loose_signature(resolved_mod)
    return out


def manifest_path(root: Path) -> Path:
    return root / "cache" / "scan-manifest.json"


def atomic_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
            json.dump(obj, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    finally:
        try:
            os.unlink(tmp)
        except FileNotFoundError:
            pass


def load_manifest(root: Path) -> dict[str, Any] | None:
    try:
        return json.loads(manifest_path(root).read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return None


def _same_metadata(path: Path, saved: dict[str, Any]) -> bool:
    st = path.stat()
    return st.st_size == saved.get("size") and st.st_mtime_ns == saved.get("mtime_ns")


def _validate_fingerprint(path: Path, saved: dict[str, Any]) -> tuple[bool, bool]:
    """Return ``(same_content, metadata_refreshed)``."""
    if _same_metadata(path, saved):
        return True, False
    if _sha256(path) != saved.get("sha256"):
        return False, False
    st = path.stat()
    saved["size"], saved["mtime_ns"] = st.st_size, st.st_mtime_ns
    return True, True


def validate_cache(root: Path) -> CacheStatus:
    m = load_manifest(root)
    if not m:
        return CacheStatus(False, "尚未解析游戏资源")
    if m.get("schema") != SCHEMA or m.get("scanner_version") != SCANNER_VERSION:
        return CacheStatus(False, "解析缓存版本已过期", str(m.get("game_dir", "")))
    try:
        game_dir = normalize_game_dir(m.get("game_dir", ""))
    except Exception as exc:
        return CacheStatus(False, f"游戏目录已失效：{exc}", str(m.get("game_dir", "")))

    changed_metadata = False
    for name in REQUIRED_GAME_FILES:
        p = game_dir / name
        saved = (m.get("files") or {}).get(name)
        if not isinstance(saved, dict):
            return CacheStatus(False, f"资源指纹缺失：{name}", str(game_dir))
        try:
            same, refreshed = _validate_fingerprint(p, saved)
        except OSError as exc:
            return CacheStatus(False, f"游戏资源无法读取：{name}: {exc}", str(game_dir))
        if not same:
            return CacheStatus(False, f"检测到游戏资源版本变化：{name}", str(game_dir))
        changed_metadata |= refreshed

    saved_archives = m.get("archive_indexes")
    if not isinstance(saved_archives, dict):
        return CacheStatus(False, "解析缓存缺少游戏归档版本信息", str(game_dir))
    current_names = {name for name in ARCHIVE_INDEX_FILES if (game_dir / name).is_file()}
    if set(saved_archives) != current_names:
        return CacheStatus(False, "检测到游戏归档集合变化", str(game_dir))
    for name in sorted(current_names):
        saved = saved_archives.get(name)
        if not isinstance(saved, dict):
            return CacheStatus(False, f"游戏归档指纹缺失：{name}", str(game_dir))
        try:
            same, refreshed = _validate_fingerprint(game_dir / name, saved)
        except OSError as exc:
            return CacheStatus(False, f"游戏归档无法读取：{name}: {exc}", str(game_dir))
        if not same:
            return CacheStatus(False, f"检测到游戏归档版本变化：{name}", str(game_dir))
        changed_metadata |= refreshed

    saved_data = m.get("archive_data")
    if not isinstance(saved_data, dict):
        return CacheStatus(False, "解析缓存缺少游戏归档数据版本信息", str(game_dir))
    current_data_names = {name for name in ARCHIVE_DATA_FILES if (game_dir / name).is_file()}
    if set(saved_data) != current_data_names:
        return CacheStatus(False, "检测到游戏归档数据集合变化", str(game_dir))
    for name in sorted(current_data_names):
        try:
            current = metadata_fingerprint(game_dir / name)
        except OSError as exc:
            return CacheStatus(False, f"游戏归档数据无法读取：{name}: {exc}", str(game_dir))
        if current != saved_data.get(name):
            return CacheStatus(False, f"检测到游戏归档数据变化：{name}", str(game_dir))

    mod_dir = m.get("mod_dir")
    expected_outputs = required_outputs(Path(mod_dir) if mod_dir else None)
    recorded_outputs = tuple(m.get("outputs") or ())
    if recorded_outputs != expected_outputs:
        return CacheStatus(False, "解析结果清单不完整或版本不匹配", str(game_dir))

    output_files = m.get("output_files") or {}
    for rel in expected_outputs:
        p = root / rel
        if not p.is_file():
            return CacheStatus(False, f"解析结果缺失：{rel}", str(game_dir))
        saved = output_files.get(rel)
        if not isinstance(saved, dict):
            return CacheStatus(False, f"解析结果指纹缺失：{rel}", str(game_dir))
        try:
            same, refreshed = _validate_fingerprint(p, saved)
        except OSError as exc:
            return CacheStatus(False, f"解析结果无法读取：{rel}: {exc}", str(game_dir))
        if not same:
            return CacheStatus(False, f"解析结果已被修改或损坏：{rel}", str(game_dir))
        changed_metadata |= refreshed

    ok, reason, tile_count = _tile_integrity(root)
    if not ok:
        return CacheStatus(False, reason, str(game_dir))
    if int(m.get("tile_count", -1)) != tile_count:
        return CacheStatus(False, "地图瓦片数量与解析记录不一致", str(game_dir))

    if mod_dir:
        mod_path = Path(mod_dir)
        r = mod_path / "regulation.bin"
        saved = m.get("mod_regulation")
        if not r.is_file() or not isinstance(saved, dict):
            return CacheStatus(False, "模组资源已失效", str(game_dir))
        try:
            same, refreshed = _validate_fingerprint(r, saved)
        except OSError as exc:
            return CacheStatus(False, f"模组 regulation.bin 无法读取：{exc}", str(game_dir))
        if not same:
            return CacheStatus(False, "检测到模组 regulation.bin 版本变化", str(game_dir))
        changed_metadata |= refreshed
        saved_loose = m.get("mod_loose")
        if not isinstance(saved_loose, dict):
            return CacheStatus(False, "解析缓存缺少模组松散文件版本信息", str(game_dir))
        if mod_loose_signature(mod_path) != saved_loose:
            return CacheStatus(False, "检测到模组松散资源变化", str(game_dir))

    if changed_metadata:
        atomic_json(manifest_path(root), m)
    return CacheStatus(True, "解析缓存有效", str(game_dir), changed_metadata)


def clear_scan_cache(root: Path) -> None:
    """Delete generated game-derived data only; preserve quests/user state."""
    for rel in GENERATED_OUTPUTS:
        p = root / rel
        if p.is_dir():
            shutil.rmtree(p, ignore_errors=True)
        else:
            try:
                p.unlink()
            except FileNotFoundError:
                pass
    icons = root / "assets" / "icons"
    if icons.is_dir():
        for p in icons.iterdir():
            if p.is_file() and (p.stem.isdigit() or p.name == "index.json"):
                p.unlink(missing_ok=True)
    manifest_path(root).unlink(missing_ok=True)


def _backup_path(root: Path) -> Path:
    return root / SCAN_BACKUP_DIR


def discard_scan_backup(root: Path) -> None:
    shutil.rmtree(_backup_path(root), ignore_errors=True)


def _move_backup_entries_back(root: Path, backup: Path, *, only_missing: bool) -> None:
    for rel in reversed(GENERATED_OUTPUTS):
        src = backup / rel
        if not src.exists():
            continue
        dst = root / rel
        if only_missing and dst.exists():
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        if dst.exists():
            if dst.is_dir():
                shutil.rmtree(dst, ignore_errors=True)
            else:
                dst.unlink(missing_ok=True)
        os.replace(src, dst)
    icon_backup = backup / "assets" / "icons"
    if icon_backup.is_dir():
        icon_dest = root / "assets" / "icons"
        icon_dest.mkdir(parents=True, exist_ok=True)
        for src in list(icon_backup.iterdir()):
            if not src.is_file():
                continue
            dst = icon_dest / src.name
            if only_missing and dst.exists():
                continue
            if dst.exists():
                dst.unlink(missing_ok=True)
            os.replace(src, dst)


def begin_scan_backup(root: Path) -> Path | None:
    """Move a currently valid generated cache aside before a new scan.

    Same-filesystem renames are effectively O(1). If any rename fails, entries
    already moved are put back before the error escapes.
    """
    status = validate_cache(root)
    if not status.valid:
        return None
    backup = _backup_path(root)
    discard_scan_backup(root)
    backup.mkdir(parents=True, exist_ok=True)
    try:
        for rel in GENERATED_OUTPUTS:
            src = root / rel
            if not src.exists():
                continue
            dst = backup / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            os.replace(src, dst)
        icons = root / "assets" / "icons"
        if icons.is_dir():
            for src in list(icons.iterdir()):
                if not src.is_file() or not (src.stem.isdigit() or src.name == "index.json"):
                    continue
                dst = backup / "assets" / "icons" / src.name
                dst.parent.mkdir(parents=True, exist_ok=True)
                os.replace(src, dst)
        (backup / SCAN_BACKUP_COMPLETE).write_text("ok\n", encoding="ascii")
    except Exception:
        _move_backup_entries_back(root, backup, only_missing=True)
        shutil.rmtree(backup, ignore_errors=True)
        raise
    return backup


def restore_scan_backup(root: Path, backup: Path | None = None) -> bool:
    """Discard partial new data and restore the previous valid cache."""
    backup = backup or _backup_path(root)
    if not backup.is_dir():
        return False
    clear_scan_cache(root)
    _move_backup_entries_back(root, backup, only_missing=False)
    shutil.rmtree(backup, ignore_errors=True)
    return True


def recover_interrupted_scan(root: Path) -> bool:
    """Recover a reparse interrupted by a hard process exit or power loss."""
    backup = _backup_path(root)
    if not backup.is_dir():
        return False
    complete = (backup / SCAN_BACKUP_COMPLETE).is_file()
    if not complete:
        # Process died while moving the old cache. Merge moved entries back and
        # leave the still-present portion untouched.
        _move_backup_entries_back(root, backup, only_missing=True)
        shutil.rmtree(backup, ignore_errors=True)
        return True
    if manifest_path(root).is_file():
        # New manifest is the final commit record; the backup is stale.
        discard_scan_backup(root)
        return False
    return restore_scan_backup(root, backup)


def validate_generated_outputs(root: Path, mod_dir: Path | None = None) -> None:
    """Validate semantic shape before writing the final success manifest."""

    def read_doc(rel: str) -> dict[str, Any]:
        path = root / rel
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            raise RuntimeError(f"解析结果 JSON 无效：{rel}: {exc}") from exc
        if not isinstance(doc, dict):
            raise RuntimeError(f"解析结果结构无效：{rel} 顶层不是对象")
        return doc

    marker_files = (
        "data/markers.json", "data/items.json", "data/unique_drops.json", "data/mausoleums.json",
    )
    seen_ids: set[str] = set()
    for rel in marker_files:
        doc = read_doc(rel)
        rows = doc.get("markers")
        if not isinstance(rows, list) or not rows:
            raise RuntimeError(f"解析结果为空或结构无效：{rel} / markers")
        for row in rows:
            if not isinstance(row, dict):
                raise RuntimeError(f"解析结果结构无效：{rel} 含非对象 marker")
            ident = str(row.get("id", ""))
            if not ident:
                raise RuntimeError(f"解析结果结构无效：{rel} 含空 marker id")
            if ident in seen_ids:
                raise RuntimeError(f"解析结果存在重复 marker id：{ident}")
            seen_ids.add(ident)
            px, py = row.get("px"), row.get("py")
            if (
                not isinstance(px, (int, float)) or isinstance(px, bool)
                or not isinstance(py, (int, float)) or isinstance(py, bool)
                or not all(math.isfinite(float(v)) for v in (px, py))
            ):
                raise RuntimeError(f"解析结果 marker 地图坐标无效：{ident}")

    catalog = read_doc("data/catalog.json")
    if not isinstance(catalog.get("items"), list) or not catalog["items"]:
        raise RuntimeError("解析结果为空或结构无效：data/catalog.json / items")

    conv = read_doc("data/legacy-conv.json")
    if not isinstance(conv.get("rows"), list) or not conv["rows"]:
        raise RuntimeError("解析结果为空或结构无效：data/legacy-conv.json / rows")

    if mod_dir:
        pieces = read_doc("data/pieces.json")
        piece_rows = pieces.get("markers")
        if not isinstance(piece_rows, list):
            raise RuntimeError("解析结果结构无效：data/pieces.json / markers")
        for row in piece_rows:
            if not isinstance(row, dict):
                raise RuntimeError("解析结果结构无效：data/pieces.json 含非对象 marker")
            ident = str(row.get("id", ""))
            px, py = row.get("px"), row.get("py")
            if (
                not ident
                or not isinstance(px, (int, float)) or isinstance(px, bool)
                or not isinstance(py, (int, float)) or isinstance(py, bool)
                or not all(math.isfinite(float(v)) for v in (px, py))
            ):
                raise RuntimeError("解析结果结构无效：data/pieces.json 含无效 marker")
            if ident in seen_ids:
                raise RuntimeError(f"解析结果存在重复 marker id：{ident}")
            seen_ids.add(ident)

    ok, reason, _ = _tile_integrity(root)
    if not ok:
        raise RuntimeError(reason)
