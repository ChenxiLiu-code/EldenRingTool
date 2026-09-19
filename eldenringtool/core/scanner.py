from __future__ import annotations

import importlib
import importlib.util
import os
import queue
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .resource_cache import (
    REQUIRED_GAME_FILES,
    archive_data_metadata,
    archive_index_signatures,
    atomic_json,
    begin_scan_backup,
    build_manifest,
    clear_scan_cache,
    discard_scan_backup,
    fingerprint,
    manifest_path,
    mod_loose_signature,
    normalize_game_dir,
    restore_scan_backup,
    same_content_signature,
    validate_generated_outputs,
)


@dataclass(frozen=True)
class Dependency:
    probes: tuple[str, ...]
    package: str
    install_spec: str


# Only dependencies used by the automatic resource scan are required here.
DEPENDENCIES = (
    Dependency(("zstandard",), "zstandard", "zstandard>=0.23"),
    Dependency(("Crypto.Cipher.AES", "Crypto.PublicKey.RSA"), "pycryptodome", "pycryptodome>=3.20"),
    Dependency(("PIL.Image",), "pillow", "pillow>=10.4"),
    Dependency(("texture2ddecoder",), "texture2ddecoder", "texture2ddecoder>=1.0"),
)


@dataclass(frozen=True)
class ScanStep:
    label: str
    argv: tuple[str, ...]
    optional: bool = False


def _module_available(module: str) -> bool:
    """Return whether an import target is discoverable without importing it.

    ``find_spec`` can raise when a dotted module's parent package is missing, so
    dependency checks must treat that as a normal "not installed" result rather
    than crashing the first-run screen.
    """
    try:
        return importlib.util.find_spec(module) is not None
    except Exception:
        return False


def _dependency_available(dep: Dependency) -> bool:
    return all(_module_available(module) for module in dep.probes)


def missing_dependencies() -> list[str]:
    return [dep.package for dep in DEPENDENCIES if not _dependency_available(dep)]


def _terminate_process(proc: subprocess.Popen[str]) -> None:
    if proc.poll() is not None:
        return
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()


def _stream_process(argv, cwd: Path, env: dict[str, str], on_log=None, cancelled=None, heartbeat_label: str | None = None) -> int:
    """Run a child process while streaming output and keeping cancellation live.

    Iterating directly over ``stdout`` can block forever when a child stalls
    without writing a newline. A small reader thread lets the worker poll the
    cancellation flag even during silent CPU/I/O work.
    """
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0
    proc = subprocess.Popen(
        argv,
        cwd=cwd,
        env=env,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
        creationflags=creationflags,
    )
    if proc.stdout is None:
        _terminate_process(proc)
        raise RuntimeError("无法读取解析子进程输出")

    lines: queue.Queue[str | None] = queue.Queue()

    def pump() -> None:
        try:
            for line in proc.stdout:
                lines.put(line)
        finally:
            lines.put(None)

    reader = threading.Thread(target=pump, name="EldenRingTool-process-log", daemon=True)
    reader.start()
    stream_done = False
    started = time.monotonic()
    last_output = started
    last_heartbeat = started
    heartbeat_after = 8.0
    heartbeat_every = 10.0
    try:
        while not stream_done:
            if cancelled and cancelled():
                _terminate_process(proc)
                raise InterruptedError("解析已取消")
            try:
                item = lines.get(timeout=0.10)
            except queue.Empty:
                now = time.monotonic()
                if (on_log and now - last_output >= heartbeat_after
                        and now - last_heartbeat >= heartbeat_every):
                    elapsed = int(now - started)
                    label = f"：{heartbeat_label}" if heartbeat_label else ""
                    on_log(f"  … 仍在执行{label}（已用时 {elapsed}s，无新日志；进程仍存活）")
                    last_heartbeat = now
                if proc.poll() is not None and not reader.is_alive():
                    break
                continue
            if item is None:
                stream_done = True
            else:
                last_output = time.monotonic()
                last_heartbeat = last_output
                if on_log:
                    on_log(item.rstrip())
        return proc.wait()
    finally:
        try:
            proc.stdout.close()
        except Exception:
            pass
        if proc.poll() is None:
            _terminate_process(proc)


def ensure_dependencies(root: Path, on_log=None, cancelled=None) -> list[str]:
    missing = missing_dependencies()
    if not missing:
        return []
    if on_log:
        on_log("缺少解析依赖：" + ", ".join(missing))
        on_log(f"当前 Python：{sys.executable}")
        for dep in DEPENDENCIES:
            if dep.package in missing:
                on_log(f"  {dep.package} -> import {', '.join(dep.probes)}")
        on_log("正在通过当前 Python 环境安装缺失的解析依赖 …")

    specs = [dep.install_spec for dep in DEPENDENCIES if dep.package in missing]
    env = os.environ.copy()
    env["PYTHONUTF8"] = "1"
    argv = (
        sys.executable,
        "-m",
        "pip",
        "install",
        "--disable-pip-version-check",
        "--no-input",
        *specs,
    )
    code = _stream_process(argv, root, env, on_log, cancelled, "安装解析依赖")
    if code:
        raise RuntimeError(f"解析依赖安装失败（pip 退出码 {code}）")
    importlib.invalidate_caches()
    remaining = missing_dependencies()
    if remaining:
        raise RuntimeError("依赖安装结束后仍缺少：" + ", ".join(remaining))
    if on_log:
        on_log("解析依赖已就绪。")
    return missing


def build_steps(root: Path, game_dir: Path, mod_dir: Path | None = None):
    py = sys.executable
    t = root / "tools"
    gd = str(game_dir)
    md = str(mod_dir) if mod_dir else ""

    def tool(name, *args):
        # ``-u`` is deliberate: GUI launches scripts through a pipe, where
        # Python would otherwise block-buffer stdout and make long scans look
        # frozen even while they are working normally.
        return (py, "-u", str(t / name), *map(str, args))

    modargs = ("--mod-dir", md) if md else ()
    return [
        ScanStep("提取地图瓦片", tool("extract_tiles.py", "--game-dir", gd, "--out", str(root / "assets" / "tiles"))),
        ScanStep("构建地图标记", tool("build_markers.py", gd)),
        ScanStep("索引地图文件", tool("enumerate_maps.py")),
        ScanStep("提取物品位置", tool("extract_items.py", "--game-dir", gd, *modargs)),
        ScanStep("提取唯一敌人/脚本奖励", tool("extract_unique_drops.py", "--game-dir", gd, *modargs)),
        ScanStep("构建收集品图鉴", tool("extract_catalog.py", "--game-dir", gd, *modargs)),
        ScanStep("提取漫步灵庙", tool("extract_mausoleums.py", "--game-dir", gd, *modargs)),
        ScanStep(
            "提取地图图标",
            tool("extract_icons.py", "--game-dir", gd, "--out", str(root / "assets" / "icons"), *modargs),
            optional=True,
        ),
        *(
            [ScanStep("提取 Reforged 符文/余火碎片", tool("extract_pieces.py", "--game-dir", gd, "--mod-dir", md))]
            if md
            else []
        ),
    ]


def _game_signatures(gd: Path) -> dict[str, dict]:
    return {name: fingerprint(gd / name) for name in REQUIRED_GAME_FILES}


def _same_signature_map(start: dict[str, dict], end: dict[str, dict]) -> bool:
    return set(start) == set(end) and all(same_content_signature(start[name], end[name]) for name in start)


def run_scan(
    root: Path,
    selected: str,
    mod_dir: str | None = None,
    on_progress: Callable[[int, int, str], None] | None = None,
    on_log: Callable[[str], None] | None = None,
    cancelled: Callable[[], bool] | None = None,
):
    root = root.resolve()
    gd = normalize_game_dir(selected)
    md = Path(mod_dir).resolve() if mod_dir else None
    if md and not (md / "regulation.bin").is_file():
        raise ValueError("模组目录缺少 regulation.bin")

    # Install parser-only dependencies before touching a previously valid cache.
    if missing_dependencies():
        if on_progress:
            on_progress(0, 1, "安装解析依赖")
        ensure_dependencies(root, on_log, cancelled)

    # Capture every resource family the parser can consume. If Steam or the mod
    # manager updates anything while extraction is running, do not commit a
    # manifest for a mixed-version result.
    start_game = _game_signatures(gd)
    start_archives = archive_index_signatures(gd)
    start_archive_data = archive_data_metadata(gd)
    start_mod = fingerprint(md / "regulation.bin") if md else None
    start_mod_loose = mod_loose_signature(md) if md else None

    # A manual reparse should be transactional: preserve the last valid cache and
    # restore it if the new parse is cancelled, fails, or detects a resource race.
    backup = begin_scan_backup(root)
    clear_scan_cache(root)

    env = os.environ.copy()
    env["PYTHONUTF8"] = "1"
    env["PYTHONUNBUFFERED"] = "1"
    env["ER_GAME_DIR"] = str(gd)
    if md:
        env["ER_MOD_DIR"] = str(md)
    else:
        env.pop("ER_MOD_DIR", None)

    try:
        steps = build_steps(root, gd, md)
        total = len(steps)
        for i, step in enumerate(steps, 1):
            if cancelled and cancelled():
                raise InterruptedError("解析已取消")
            if on_progress:
                on_progress(i, total, step.label)
            if on_log:
                on_log(f"[{i}/{total}] {step.label}")
            code = _stream_process(step.argv, root, env, on_log, cancelled, step.label)
            if code and not step.optional:
                raise RuntimeError(f"{step.label}失败（退出码 {code}）")
            if code and on_log:
                on_log(f"可选步骤失败，继续：{step.label}")

        end_game = _game_signatures(gd)
        for name in REQUIRED_GAME_FILES:
            if not same_content_signature(start_game[name], end_game[name]):
                raise RuntimeError(f"解析期间游戏资源发生变化：{name}；本次结果不会标记为有效，请重新解析")

        end_archives = archive_index_signatures(gd)
        if not _same_signature_map(start_archives, end_archives):
            raise RuntimeError("解析期间游戏归档索引发生变化；本次结果不会标记为有效，请重新解析")
        if archive_data_metadata(gd) != start_archive_data:
            raise RuntimeError("解析期间游戏归档数据发生变化；本次结果不会标记为有效，请重新解析")

        if md:
            end_mod = fingerprint(md / "regulation.bin")
            if not same_content_signature(start_mod or {}, end_mod):
                raise RuntimeError("解析期间模组 regulation.bin 发生变化；本次结果不会标记为有效，请重新解析")
            if mod_loose_signature(md) != start_mod_loose:
                raise RuntimeError("解析期间模组松散资源发生变化；本次结果不会标记为有效，请重新解析")

        # A child script returning 0 is not enough. Reject structurally empty or
        # corrupt corpora before the success manifest becomes the commit record.
        validate_generated_outputs(root, md)

        manifest = build_manifest(root, gd, md, game_files=end_game)
        atomic_json(manifest_path(root), manifest)
        discard_scan_backup(root)
        if on_progress:
            on_progress(total, total, "解析完成")
        return manifest
    except BaseException:
        if backup is not None:
            restore_scan_backup(root, backup)
        else:
            # No old valid cache existed; leave no partial success marker/data.
            clear_scan_cache(root)
        raise
