#!/usr/bin/env python3
"""Pre-compute each marker's vertical offset from the real overworld surface.

Primary geometry source: Elden Ring MapPiece FLVER render geometry referenced by
the tile MSB. MapPiece geometry is transformed through FLVER bones and the MSB
part transform, then queried with vertical rays. A neighbourhood layer-consensus
step rejects isolated roofs/bridges when broad terrain continues below them.

Fallback geometry source: NVMHKT navigation meshes through Soulstruct-Havok.
This path is retained only for markers that the FLVER provider cannot resolve.
If hk2018 types are unsupported, the existing circuit breaker disables the
fallback quickly and unresolved markers are simply left without surface data.

The tool is read-only with respect to game files. It updates only generated JSON
under data/ and writes diagnostics to cache/surface-height-report.json.
"""
from __future__ import annotations

import argparse
import contextlib
import io
import json
import logging
import math
import os
import re
import sys
import time
import traceback
from collections import OrderedDict, defaultdict
from dataclasses import dataclass
from pathlib import Path
from statistics import median
from typing import Iterable, Sequence

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))


TILE_WORLD = 256.0
OFFSET_X = -7168.0
OFFSET_Y = 16640.0

# These legacy maps are intentionally drawn at arbitrary world-map positions.
# Comparing their Y coordinate with the overworld terrain under that drawing is
# physically meaningless, so we leave them unannotated rather than manufacture
# a very precise-looking wrong number.
DETACHED_LEGACY_PREFIXES = (
    "m13_00",  # Crumbling Farum Azula
    "m15_00",  # Miquella's Haligtree / Elphael map-art placement
    "m25_00",  # Finger Birthing Grounds / detached map-art placement
)

# Generated files that contribute markers to the native application. Every file is
# optional; Setup versions predating a particular extractor still work.
MARKER_FILES = (
    "markers.json",
    "items.json",
    "unique_drops.json",
    "mausoleums.json",
    "pieces.json",
)

# Neighbour rays establish which vertical layer is broad terrain rather than an
# isolated roof/bridge. The outer ring makes the decision robust around large
# buildings without constructing a global height field.
NEIGHBOUR_RINGS = (16.0, 36.0, 64.0)
NEIGHBOUR_DIRECTIONS = 8
MIN_LAYER_SUPPORT = 7
LAYER_BASE_TOLERANCE = 5.0
LAYER_SLOPE_TOLERANCE = 0.55

# FLVER/MSBE constants. These offsets are the common MSBE part/model header
# layout used by Elden Ring. MapPiece subtype is zero for both MODEL and PARTS.
PART_SUBTYPE = 0x0C
PART_MODEL_INDEX = 0x14
PART_POSITION = 0x20
PART_ROTATION = 0x2C
PART_SCALE = 0x38
MAPPIECE_SUBTYPE = 0
FLVER_TILE_CACHE = 4
FLVER_MODEL_CACHE = 48
SPATIAL_CELL = 32.0
MIN_UP_NORMAL = 0.20


def _missing_havok_types(exc: BaseException) -> tuple[str, ...]:
    """Extract missing Havok class names from Soulstruct's TypeNotDefinedError text."""
    text = str(exc)
    found = set(re.findall(r"Type\s+([A-Za-z_][A-Za-z0-9_]*)\s+is not defined", text))
    # Newer unpacker path can report a batch: ``Types:['A', 'B']``.
    batch = re.search(r"Types:\s*\[([^]]*)\]", text)
    if batch:
        found.update(re.findall(r"['\"]([A-Za-z_][A-Za-z0-9_]*)['\"]", batch.group(1)))
    return tuple(sorted(found))


@contextlib.contextmanager
def _quiet_havok_parse():
    """Suppress Soulstruct's speculative parse traceback/log spam.

    ``HKX.from_bytes`` prints a traceback *before* re-raising. For NVMHKT we
    intentionally probe many binder entries and handle unsupported entries
    ourselves, so those internal tracebacks are noise rather than fatal errors.
    """
    logger_names = ("soulstruct.havok.core", "soulstruct.havok.tagfile.unpacker")
    loggers = [logging.getLogger(name) for name in logger_names]
    old_disabled = [logger.disabled for logger in loggers]
    try:
        for logger in loggers:
            logger.disabled = True
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            yield
    finally:
        for logger, disabled in zip(loggers, old_disabled):
            logger.disabled = disabled


@dataclass(slots=True)
class Triangles:
    """World-space triangles with a compact X/Z uniform-grid acceleration index."""

    vertices: np.ndarray  # (N, 3, 3), float32 XYZ per triangle
    min_x: np.ndarray
    max_x: np.ndarray
    min_z: np.ndarray
    max_z: np.ndarray
    cell_size: float
    bins: dict[tuple[int, int], np.ndarray]

    @classmethod
    def from_triangles(cls, triangles: np.ndarray, cell_size: float = SPATIAL_CELL) -> "Triangles":
        triangles = np.asarray(triangles, dtype=np.float32)
        if triangles.size == 0:
            triangles = np.empty((0, 3, 3), dtype=np.float32)
        xs = triangles[:, :, 0]
        zs = triangles[:, :, 2]
        min_x = xs.min(axis=1) if len(triangles) else np.empty(0, dtype=np.float32)
        max_x = xs.max(axis=1) if len(triangles) else np.empty(0, dtype=np.float32)
        min_z = zs.min(axis=1) if len(triangles) else np.empty(0, dtype=np.float32)
        max_z = zs.max(axis=1) if len(triangles) else np.empty(0, dtype=np.float32)

        # A vertical ray only needs triangles whose top-down AABB overlaps its
        # grid cell. Building once per map tile is much cheaper than testing all
        # map-piece triangles for every marker/neighbour ray.
        tmp: dict[tuple[int, int], list[int]] = defaultdict(list)
        if cell_size > 0:
            for i in range(len(triangles)):
                ix0, ix1 = math.floor(float(min_x[i]) / cell_size), math.floor(float(max_x[i]) / cell_size)
                iz0, iz1 = math.floor(float(min_z[i]) / cell_size), math.floor(float(max_z[i]) / cell_size)
                # Pathological huge faces are rare. Limit index expansion and
                # let them fall back to the tile-wide sentinel bin instead.
                if (ix1 - ix0 + 1) * (iz1 - iz0 + 1) > 256:
                    tmp[(2**30, 2**30)].append(i)
                    continue
                for ix in range(ix0, ix1 + 1):
                    for iz in range(iz0, iz1 + 1):
                        tmp[(ix, iz)].append(i)
        bins = {k: np.asarray(v, dtype=np.int32) for k, v in tmp.items()}
        return cls(triangles, min_x, max_x, min_z, max_z, float(cell_size), bins)

    def _candidates(self, x: float, z: float) -> np.ndarray:
        if not len(self.vertices):
            return np.empty(0, dtype=np.int32)
        if not self.bins or self.cell_size <= 0:
            return np.arange(len(self.vertices), dtype=np.int32)
        key = (math.floor(x / self.cell_size), math.floor(z / self.cell_size))
        local = self.bins.get(key)
        huge = self.bins.get((2**30, 2**30))
        if local is None:
            return huge if huge is not None else np.empty(0, dtype=np.int32)
        if huge is None or len(huge) == 0:
            return local
        return np.concatenate((local, huge))

    def ray_heights(self, x: float, z: float) -> list[float]:
        """All vertical-ray intersections at X/Z, deduplicated and high->low."""
        ids = self._candidates(x, z)
        if len(ids) == 0:
            return []
        eps = 1e-5
        ids = ids[
            (self.min_x[ids] - eps <= x) & (x <= self.max_x[ids] + eps)
            & (self.min_z[ids] - eps <= z) & (z <= self.max_z[ids] + eps)
        ]
        if len(ids) == 0:
            return []
        tri = self.vertices[ids].astype(np.float64, copy=False)
        x1, y1, z1 = tri[:, 0, 0], tri[:, 0, 1], tri[:, 0, 2]
        x2, y2, z2 = tri[:, 1, 0], tri[:, 1, 1], tri[:, 1, 2]
        x3, y3, z3 = tri[:, 2, 0], tri[:, 2, 1], tri[:, 2, 2]
        den = (z2 - z3) * (x1 - x3) + (x3 - x2) * (z1 - z3)
        good = np.abs(den) > 1e-9
        if not np.any(good):
            return []
        den = den[good]
        x1, y1, z1 = x1[good], y1[good], z1[good]
        x2, y2, z2 = x2[good], y2[good], z2[good]
        x3, y3, z3 = x3[good], y3[good], z3[good]
        a = ((z2 - z3) * (x - x3) + (x3 - x2) * (z - z3)) / den
        b = ((z3 - z1) * (x - x3) + (x1 - x3) * (z - z3)) / den
        c = 1.0 - a - b
        inside = (a >= -1e-6) & (b >= -1e-6) & (c >= -1e-6)
        if not np.any(inside):
            return []
        ys = a[inside] * y1[inside] + b[inside] * y2[inside] + c[inside] * y3[inside]
        out: list[float] = []
        for value in sorted((float(v) for v in ys if math.isfinite(float(v))), reverse=True):
            if not out or abs(value - out[-1]) > 0.20:
                out.append(value)
        return out

def triangulate(vertices: np.ndarray, faces: Sequence[Sequence[int]]) -> np.ndarray:
    """Fan-triangulate Havok navmesh polygons (which are normally convex)."""
    verts = np.asarray(vertices, dtype=np.float64)
    triangles = []
    for face in faces:
        if len(face) < 3:
            continue
        a = int(face[0])
        for i in range(1, len(face) - 1):
            ids = (a, int(face[i]), int(face[i + 1]))
            try:
                tri = verts[list(ids), :3]
            except (IndexError, TypeError):
                continue
            # Ignore faces with essentially no top-down area. A vertical wall
            # cannot define a terrain height for a vertical ray.
            area2 = abs(
                (tri[1, 0] - tri[0, 0]) * (tri[2, 2] - tri[0, 2])
                - (tri[2, 0] - tri[0, 0]) * (tri[1, 2] - tri[0, 2])
            )
            if area2 > 1e-6:
                triangles.append(tri)
    return np.asarray(triangles, dtype=np.float64) if triangles else np.empty((0, 3, 3))


def map_id_for_world(area: int, world_x: float, world_z: float, tier: int) -> str:
    """Return m60/m61 tile id covering a world point at the requested tier."""
    size = TILE_WORLD * (2 ** tier)
    gx = math.floor(world_x / size)
    gz = math.floor(world_z / size)
    return f"m{area:02d}_{gx:02d}_{gz:02d}_{tier:02d}"


def tile_bounds(map_id: str) -> tuple[float, float, float, float, float, float]:
    parts = map_id[1:].split("_")
    area, gx, gz, tier = map(int, parts)
    size = TILE_WORLD * (2 ** tier)
    x0, z0 = gx * size, gz * size
    return x0, x0 + size, z0, z0 + size, x0 + size / 2, z0 + size / 2


def choose_world_offset(vertices: np.ndarray, map_id: str) -> tuple[float, float, str]:
    """Infer whether one NVMHKT binder exposes world-, centre-, or corner-local X/Z.

    Soulstruct returns native FromSoftware XYZ coordinates. Different resources
    and tool versions have historically exposed tile-local/world coordinates in
    different contexts, so we infer the frame from the binder's own bounds
    rather than hardcoding a single assumption.
    """
    x0, x1, z0, z1, cx, cz = tile_bounds(map_id)
    size = x1 - x0
    if len(vertices) == 0:
        return 0.0, 0.0, "world"
    sample = vertices if len(vertices) <= 20000 else vertices[:: max(1, len(vertices) // 20000)]
    candidates = (
        (0.0, 0.0, "world"),
        (cx, cz, "center-local"),
        (x0, z0, "corner-local"),
    )
    best = None
    for ox, oz, label in candidates:
        xs = sample[:, 0] + ox
        zs = sample[:, 2] + oz
        med_x, med_z = float(np.median(xs)), float(np.median(zs))
        centre_error = abs(med_x - cx) / max(size, 1.0) + abs(med_z - cz) / max(size, 1.0)
        margin = size * 0.35
        inside = ((x0 - margin <= xs) & (xs <= x1 + margin)
                  & (z0 - margin <= zs) & (zs <= z1 + margin))
        outside_penalty = 2.5 * (1.0 - float(np.mean(inside)))
        score = centre_error + outside_penalty
        if best is None or score < best[0]:
            best = (score, ox, oz, label)
    assert best is not None
    return best[1], best[2], best[3]


def _entry_bytes(bnd, entry, oodle_helper) -> bytes:
    from erlib import dcx
    raw = bnd.data[entry.data_offset: entry.data_offset + entry.size]
    return dcx.decompress(raw, oodle=oodle_helper) if dcx.is_dcx(raw) else raw



def _rotation_matrix_xzy_deg(rotation: Sequence[float]) -> np.ndarray:
    """FromSoftware Euler order (X -> Z -> Y), returned for column-vector use."""
    rx, ry, rz = (math.radians(float(v)) for v in rotation)
    sx, cx = math.sin(rx), math.cos(rx)
    sy, cy = math.sin(ry), math.cos(ry)
    sz, cz = math.sin(rz), math.cos(rz)
    mx = np.array([[1.0, 0.0, 0.0], [0.0, cx, -sx], [0.0, sx, cx]], dtype=np.float64)
    my = np.array([[cy, 0.0, sy], [0.0, 1.0, 0.0], [-sy, 0.0, cy]], dtype=np.float64)
    mz = np.array([[cz, -sz, 0.0], [sz, cz, 0.0], [0.0, 0.0, 1.0]], dtype=np.float64)
    return my @ mz @ mx


def _apply_part_transform(triangles: np.ndarray, translate, rotate, scale, map_id: str) -> np.ndarray:
    """Transform model-local FLVER triangles into the same world frame as markers."""
    if not len(triangles):
        return np.empty((0, 3, 3), dtype=np.float32)
    points = np.asarray(triangles, dtype=np.float64).reshape((-1, 3)).copy()
    sc = np.asarray(scale, dtype=np.float64)
    if not np.all(np.isfinite(sc)) or np.any(np.abs(sc) < 1e-9):
        return np.empty((0, 3, 3), dtype=np.float32)
    points *= sc
    points = points @ _rotation_matrix_xzy_deg(rotate).T
    points += np.asarray(translate, dtype=np.float64)
    # Overworld MSB coordinates are tile-centred local coordinates. This is the
    # same convention used by build_markers.project() for event/part positions.
    *_, cx, cz = tile_bounds(map_id)
    points[:, 0] += cx
    points[:, 2] += cz
    return points.reshape((-1, 3, 3)).astype(np.float32, copy=False)


def _filter_surface_triangles(triangles: np.ndarray) -> np.ndarray:
    """Drop degenerate/near-vertical faces that cannot represent broad ground."""
    tri = np.asarray(triangles, dtype=np.float32)
    if tri.size == 0:
        return np.empty((0, 3, 3), dtype=np.float32)
    e1 = tri[:, 1] - tri[:, 0]
    e2 = tri[:, 2] - tri[:, 0]
    normals = np.cross(e1, e2)
    norm = np.linalg.norm(normals, axis=1)
    up = np.abs(normals[:, 1]) / np.maximum(norm, 1e-12)
    top_area = np.abs(normals[:, 1])
    finite = np.all(np.isfinite(tri), axis=(1, 2))
    keep = finite & (norm > 1e-7) & (top_area > 1e-6) & (up >= MIN_UP_NORMAL)
    return tri[keep]


def _flver_local_triangles(flver) -> np.ndarray:
    """Extract bone-transformed local triangles from one static MapPiece FLVER.

    This deliberately uses only the primary face set exposed by Soulstruct's
    ``mesh.triangulate_flver2()``. Secondary face sets are LOD/motion-blur copies
    in normal Elden Ring map pieces and would otherwise duplicate geometry.
    """
    try:
        from soulstruct.flver.bone_tools import BoneTree
    except Exception as exc:  # pragma: no cover - dependency checked by Setup
        raise RuntimeError(f"Soulstruct FLVER bone tools unavailable: {exc}") from exc

    transforms = []
    if getattr(flver, "bones", None):
        try:
            transforms = BoneTree(flver).get_bone_armature_space_transforms()
        except Exception:
            # A malformed hierarchy should not kill the whole tile. Local bone
            # transforms are still better than ignoring all geometry.
            for bone in flver.bones:
                from soulstruct.utilities.maths import Matrix3
                transforms.append((bone.translate, Matrix3.from_euler_angles_rad(bone.rotate, order="xzy"), bone.scale))

    all_triangles: list[np.ndarray] = []
    for mesh in getattr(flver, "meshes", ()):
        arrays = [va for va in getattr(mesh, "vertex_arrays", ()) if va.has_field("position")]
        if not arrays:
            continue
        va = arrays[0]
        positions = np.asarray(va["position"], dtype=np.float64).copy()
        if not len(positions):
            continue

        # Static map pieces generally bind each vertex to one bone. Soulstruct's
        # own debone_map_piece() uses this exact first-index/normal_w convention.
        if transforms:
            if va.has_field("bone_indices"):
                local_indices = np.asarray(va["bone_indices"][:, 0], dtype=np.int64)
            elif getattr(va, "guess_has_normal_w_bone_indices", False) and va.has_field("normal_w"):
                normal_w = np.asarray(va["normal_w"])
                local_indices = np.asarray(normal_w[:, 0] if normal_w.ndim > 1 else normal_w, dtype=np.int64)
            else:
                default = int(getattr(mesh, "default_bone_index", 0) or 0)
                local_indices = np.full(len(positions), max(0, default), dtype=np.int64)

            mesh_bones = getattr(mesh, "bone_indices", None)
            if mesh_bones is not None and len(mesh_bones):
                table = np.asarray(mesh_bones, dtype=np.int64)
                safe = np.clip(local_indices, 0, len(table) - 1)
                global_indices = table[safe]
            else:
                global_indices = local_indices

            for bone_i in np.unique(global_indices):
                bi = int(bone_i)
                if bi < 0 or bi >= len(transforms):
                    continue
                mask = global_indices == bi
                t, r, sc = transforms[bi]
                t_data = np.asarray(getattr(t, "data", t), dtype=np.float64)
                r_data = np.asarray(getattr(r, "data", r), dtype=np.float64)
                s_data = np.asarray(getattr(sc, "data", sc), dtype=np.float64)
                positions[mask] = (s_data * positions[mask]) @ r_data.T + t_data

        try:
            if getattr(flver.version, "is_flver0", lambda: False)():
                faces = mesh.triangulate_flver0()
            else:
                faces = mesh.triangulate_flver2()
        except Exception:
            continue
        faces = np.asarray(faces, dtype=np.int64)
        if faces.ndim != 2 or faces.shape[1] != 3 or not len(faces):
            continue
        valid = np.all((faces >= 0) & (faces < len(positions)), axis=1)
        if np.any(valid):
            all_triangles.append(positions[faces[valid]])

    if not all_triangles:
        return np.empty((0, 3, 3), dtype=np.float32)
    return _filter_surface_triangles(np.concatenate(all_triangles, axis=0))


class FLVERTerrainSource:
    """Primary surface provider: MSB MapPiece placements + FLVER render geometry."""

    method_prefix = "flver"

    def __init__(self, game_dir: str, mod_dir: str | None, cache_size: int = FLVER_TILE_CACHE):
        from erlib import oodle
        from erlib.dvdbnd import DvdBnd
        try:
            from soulstruct.flver import FLVER
        except Exception as exc:
            raise RuntimeError(f"Soulstruct FLVER support unavailable: {exc}") from exc
        self.FLVER = FLVER
        self.game_dir = game_dir
        self.mod_dir = mod_dir
        self.dvd = DvdBnd(game_dir, cache_dir=str(ROOT / "cache" / "bhd"), verbose=False)
        self.oodle = oodle.make_helper(game_dir)
        self.cache_size = max(2, int(cache_size))
        self.cache: OrderedDict[str, Triangles | None] = OrderedDict()
        self.model_cache: OrderedDict[tuple[str, str], np.ndarray | None] = OrderedDict()
        self.errors: dict[str, str] = {}
        self.model_errors: dict[str, str] = {}
        self.successful_tiles = 0
        self.attempted_tiles = 0
        self.tiles_with_map_pieces = 0
        self.missing_models = 0
        self.missing_model_examples: list[str] = []
        self.parsed_models = 0
        self.disabled_reason: str | None = None

    def close(self):
        self.dvd.close()

    @staticmethod
    def _model_paths(map_id: str, model_name: str) -> tuple[str, ...]:
        """Return plausible retail/loose paths for one MapPiece FLVER.

        FromSoft tooling has exposed Elden Ring map pieces both directly below
        ``map/<map_id>`` and below an area grouping such as ``map/m60/<map_id>``.
        The DVD archives are hash-indexed, so trying a few exact candidates is
        cheap and much safer than committing Setup to one extraction layout.
        """
        model = str(model_name).replace("\\", "/").rsplit("/", 1)[-1]
        # Strip both extensions in the correct order. ``foo.flver.dcx`` must not
        # accidentally become ``foo.flver.flver.dcx``.
        if model.lower().endswith(".dcx"):
            model = model[:-4]
        if model.lower().endswith(".flver"):
            model = model[:-6]

        match = re.match(r"(m\d{2}_\d{2}_\d{2}_\d{2})", model, re.IGNORECASE)
        model_map = match.group(1).lower() if match else map_id
        roots = [
            # Soulstruct's native map-piece layout is map/<map_id>/<model>.
            f"/map/{map_id}",
            # Retail/open-world mirrors are also commonly grouped by m60/m61.
            f"/map/{map_id[:3]}/{map_id}",
            f"/map/{model_map}",
            f"/map/{model_map[:3]}/{model_map}",
            # Defensive fallbacks for unpackers/mod mirrors that flatten one or
            # both map-directory levels. The model stem is globally specific.
            f"/map/{map_id[:3]}",
            f"/map/{model_map[:3]}",
            "/map",
        ]
        out: list[str] = []
        for root in roots:
            for suffix in (".flver.dcx", ".flver"):
                path = f"{root}/{model}{suffix}"
                if path not in out:
                    out.append(path)
        return tuple(out)

    def _read_model(self, map_id: str, model_name: str) -> np.ndarray | None:
        from erlib import dcx
        import erlib.modfiles as modfiles
        key = (map_id, model_name.lower())
        if key in self.model_cache:
            value = self.model_cache.pop(key)
            self.model_cache[key] = value
            return value

        value = None
        found_path = None
        for path in self._model_paths(map_id, model_name):
            if modfiles.has(self.dvd, self.mod_dir, path):
                found_path = path
                break
        if found_path is None:
            self.missing_models += 1
            if len(self.missing_model_examples) < 50:
                self.missing_model_examples.append(f"{map_id}:{model_name}")
        else:
            try:
                packed = modfiles.read(self.dvd, self.mod_dir, found_path)
                raw = dcx.decompress(packed, oodle=self.oodle) if dcx.is_dcx(packed) else packed
                flver = self.FLVER.from_bytes(raw)
                value = _flver_local_triangles(flver)
                if value is not None and len(value):
                    self.parsed_models += 1
                else:
                    value = None
                    self.model_errors[found_path] = "FLVER contained no usable surface triangles"
            except Exception as exc:
                self.model_errors[found_path] = f"{type(exc).__name__}: {exc}"
                value = None

        self.model_cache[key] = value
        while len(self.model_cache) > FLVER_MODEL_CACHE:
            self.model_cache.popitem(last=False)
        return value

    def get_tile(self, map_id: str) -> Triangles | None:
        if map_id in self.cache:
            value = self.cache.pop(map_id)
            self.cache[map_id] = value
            return value
        value = self._load_tile(map_id)
        self.cache[map_id] = value
        while len(self.cache) > self.cache_size:
            self.cache.popitem(last=False)
        return value

    def _load_tile(self, map_id: str) -> Triangles | None:
        if self.disabled_reason:
            return None
        started = time.perf_counter()
        from erlib import dcx
        from erlib import msb as msblib
        import erlib.modfiles as modfiles

        self.attempted_tiles += 1
        msb_path = f"/map/mapstudio/{map_id}.msb.dcx"
        if not modfiles.has(self.dvd, self.mod_dir, msb_path):
            return None
        try:
            packed = modfiles.read(self.dvd, self.mod_dir, msb_path)
            msb = msblib.load(dcx.decompress(packed, oodle=self.oodle))
        except Exception as exc:
            self.errors[map_id] = f"MSB {type(exc).__name__}: {exc}"
            return None

        model_entries = msb.lists.get("MODEL_PARAM_ST")
        part_entries = msb.lists.get("PARTS_PARAM_ST")
        if not model_entries or not part_entries:
            return None
        model_offsets = model_entries.entry_offsets
        model_names = [msb.entry_name(off) for off in model_offsets]

        placements = []
        for off in part_entries.entry_offsets:
            if off <= 0 or off + PART_SCALE + 12 > len(msb.data):
                continue
            try:
                if msb.i32(off + PART_SUBTYPE) != MAPPIECE_SUBTYPE:
                    continue
                model_index = msb.i32(off + PART_MODEL_INDEX)
                if not (0 <= model_index < len(model_names)):
                    continue
                model_name = model_names[model_index]
                if not model_name:
                    continue
                placements.append((
                    model_name,
                    msb.vec3(off + PART_POSITION),
                    msb.vec3(off + PART_ROTATION),
                    msb.vec3(off + PART_SCALE),
                ))
            except (IndexError, ValueError, OverflowError):
                continue

        if not placements:
            return None
        self.tiles_with_map_pieces += 1
        world_tris = []
        loaded_placements = 0
        local_models: dict[str, np.ndarray | None] = {}
        for model_name, translate, rotate, scale in placements:
            model_key = model_name.lower()
            if model_key not in local_models:
                local_models[model_key] = self._read_model(map_id, model_name)
            local = local_models[model_key]
            if local is None or not len(local):
                continue
            loaded_placements += 1
            transformed = _apply_part_transform(local, translate, rotate, scale, map_id)
            if len(transformed):
                world_tris.append(transformed)

        if not world_tris:
            self.errors[map_id] = f"{len(placements)} MapPiece placements but no readable FLVER geometry"
            # If several real MapPiece tiles all fail before one success, the
            # archive path/layout or FLVER parser is systematically incompatible.
            failed_piece_tiles = self.tiles_with_map_pieces - self.successful_tiles
            if self.successful_tiles == 0 and failed_piece_tiles >= 3 and not self.disabled_reason:
                self.disabled_reason = (
                    "MapPiece FLVER geometry could not be read from three independent overworld tiles"
                )
                print(
                    "WARNING: " + self.disabled_reason
                    + "; switching to NVMHKT fallback where available.",
                    flush=True,
                )
            return None

        triangles = _filter_surface_triangles(np.concatenate(world_tris, axis=0))
        if not len(triangles):
            self.errors[map_id] = "MapPiece FLVER geometry had no upward-facing surface triangles"
            return None
        self.successful_tiles += 1
        indexed = Triangles.from_triangles(triangles)
        elapsed = time.perf_counter() - started
        print(
            f"  FLVER {map_id}: {len(placements):,} MapPiece placements, "
            f"{loaded_placements:,} resolved, {len(local_models):,} unique models, "
            f"{len(triangles):,} surface triangles ({elapsed:.1f}s)",
            flush=True,
        )
        return indexed

    @staticmethod
    def _fine_neighbor_ids(area: int, world_x: float, world_z: float) -> tuple[str, ...]:
        """Tier-0 neighbours used only when the containing tile has no ray hit.

        A MapPiece may straddle an MSB tile seam even though the query point is
        geometrically inside the neighbouring part. Loading neighbours lazily
        avoids seam holes without multiplying the normal fast path cost.
        """
        gx = math.floor(world_x / TILE_WORLD)
        gz = math.floor(world_z / TILE_WORLD)
        offsets = ((-1, 0), (1, 0), (0, -1), (0, 1),
                   (-1, -1), (-1, 1), (1, -1), (1, 1))
        return tuple(f"m{area:02d}_{gx + dx:02d}_{gz + dz:02d}_00" for dx, dz in offsets)

    def _candidate_tiles(self, area: int, world_x: float, world_z: float):
        # Tier 0 is authoritative detailed geometry. Check the containing tile
        # first; seam neighbours are lazy fallbacks, then coarser parent tiles.
        seen: set[str] = set()
        primary = map_id_for_world(area, world_x, world_z, 0)
        seen.add(primary)
        mesh = self.get_tile(primary)
        if mesh is not None:
            yield primary, mesh
        for map_id in self._fine_neighbor_ids(area, world_x, world_z):
            if map_id in seen:
                continue
            seen.add(map_id)
            mesh = self.get_tile(map_id)
            if mesh is not None:
                yield map_id, mesh
        for tier in (1, 2):
            map_id = map_id_for_world(area, world_x, world_z, tier)
            if map_id in seen:
                continue
            seen.add(map_id)
            mesh = self.get_tile(map_id)
            if mesh is not None:
                yield map_id, mesh

    def ray_heights(self, area: int, world_x: float, world_z: float) -> tuple[list[float], str | None]:
        for map_id, mesh in self._candidate_tiles(area, world_x, world_z):
            hits = mesh.ray_heights(world_x, world_z)
            if hits:
                return hits, map_id
        return [], None

    def report(self) -> dict:
        return {
            "disabledReason": self.disabled_reason,
            "attemptedTiles": self.attempted_tiles,
            "successfulTiles": self.successful_tiles,
            "tilesWithMapPieces": self.tiles_with_map_pieces,
            "parsedModels": self.parsed_models,
            "missingModels": self.missing_models,
            "missingModelExamples": self.missing_model_examples,
            "tileErrors": self.errors,
            "modelErrors": self.model_errors,
        }

class NavmeshSource:
    """Secondary surface provider: overworld NVMHKT binders through Soulstruct-Havok."""

    method_prefix = "navmesh"

    def __init__(self, game_dir: str, mod_dir: str | None, cache_size: int = 10):
        from erlib import oodle
        from erlib.dvdbnd import DvdBnd
        self.game_dir = game_dir
        self.mod_dir = mod_dir
        self.dvd = DvdBnd(game_dir, cache_dir=str(ROOT / "cache" / "bhd"), verbose=False)
        self.oodle = oodle.make_helper(game_dir)
        self.cache_size = cache_size
        self.cache: OrderedDict[str, Triangles | None] = OrderedDict()
        self.errors: dict[str, str] = {}
        self.frames: dict[str, str] = {}
        # Heavy GPL dependency is Setup-only and intentionally lazy, so all
        # other project tools can still import this module for geometry tests.
        try:
            from soulstruct.havok.core import HKX
            from soulstruct.havok.exceptions import TypeNotDefinedError
            from soulstruct.havok.fromsoft.eldenring.file_types import NavmeshHKX
        except Exception as exc:
            raise RuntimeError(
                "NVMHKT support requires Python 3.13 and parser dependencies. "
                "Start EldenRingTool with bootstrap.py/Run_EldenRingTool.bat and let the parser install "
                f"soulstruct 2.4.3 + soulstruct-havok 1.3.2. Import error: {exc}"
            ) from exc
        self.HKX = HKX
        self.NavmeshHKX = NavmeshHKX
        self.TypeNotDefinedError = TypeNotDefinedError
        self.successful_tiles = 0
        self.unsupported_tiles = 0
        self.unsupported_tile_ids: set[str] = set()
        self.unsupported_types: dict[str, int] = defaultdict(int)
        self.disabled_reason: str | None = None

    def close(self):
        self.dvd.close()

    def _note_unsupported_tile(self, map_id: str, missing: Sequence[str]) -> None:
        """Record one tile blocked by missing Soulstruct hk2018 definitions.

        Stop globally only after several independent tiles fail before any tile
        succeeds. This distinguishes a stray unsupported binder payload from a
        systemic parser/game-version mismatch.
        """
        names = tuple(sorted(set(missing))) or ("<unknown>",)
        if map_id in self.unsupported_tile_ids:
            return
        self.unsupported_tile_ids.add(map_id)
        self.unsupported_tiles = len(self.unsupported_tile_ids)
        for name in names:
            self.unsupported_types[name] = self.unsupported_types.get(name, 0) + 1
        self.errors[map_id] = "Soulstruct Havok unsupported types: " + ", ".join(names)
        if self.successful_tiles == 0 and self.unsupported_tiles >= 3 and not self.disabled_reason:
            top = ", ".join(
                name for name, _ in sorted(
                    self.unsupported_types.items(), key=lambda kv: (-kv[1], kv[0])
                )[:6]
            )
            self.disabled_reason = (
                "Soulstruct-Havok cannot decode this game's NVMHKT type set"
                + (f" (missing: {top})" if top else "")
            )
            print(
                "WARNING: " + self.disabled_reason
                + "; surface-height enhancement will be skipped. Core map data remains valid.",
                flush=True,
            )

    def _paths(self, map_id: str) -> tuple[str, ...]:
        """Candidate archive layouts used by Elden Ring map resources.

        Retail archives normally group overworld tiles under /map/m60 or
        /map/m61, while some extracted/mod layouts and older tooling expose
        the tile directly below /map. Supporting both makes Setup robust to
        vanilla archives as well as loose-file mod mirrors.
        """
        area_dir = map_id[:3]  # m60 / m61
        return (
            f"/map/{area_dir}/{map_id}/{map_id}.nvmhktbnd.dcx",
            f"/map/{map_id}/{map_id}.nvmhktbnd.dcx",
        )

    def _existing_path(self, map_id: str) -> str | None:
        import erlib.modfiles as modfiles
        for path in self._paths(map_id):
            if modfiles.has(self.dvd, self.mod_dir, path):
                return path
        return None

    def has_tile(self, map_id: str) -> bool:
        return self._existing_path(map_id) is not None

    def get_tile(self, map_id: str) -> Triangles | None:
        if map_id in self.cache:
            value = self.cache.pop(map_id)
            self.cache[map_id] = value
            return value
        value = self._load_tile(map_id)
        self.cache[map_id] = value
        while len(self.cache) > self.cache_size:
            self.cache.popitem(last=False)
        return value

    def _load_tile(self, map_id: str) -> Triangles | None:
        if self.disabled_reason:
            return None
        started = time.perf_counter()
        from erlib import dcx
        from erlib.bnd4 import BND4
        import erlib.modfiles as modfiles
        path = self._existing_path(map_id)
        if path is None:
            return None
        try:
            packed = modfiles.read(self.dvd, self.mod_dir, path)
            unpacked = dcx.decompress(packed, oodle=self.oodle)
            bnd = BND4(unpacked)

            compendium = None
            for entry in bnd.entries:
                if not entry.name.lower().endswith(".compendium"):
                    continue
                try:
                    with _quiet_havok_parse():
                        compendium = self.HKX.from_bytes(_entry_bytes(bnd, entry, self.oodle))
                except self.TypeNotDefinedError as exc:
                    self._note_unsupported_tile(map_id, _missing_havok_types(exc))
                    return None
                break

            meshes: list[tuple[np.ndarray, Sequence[Sequence[int]]]] = []
            parse_errors = 0
            missing_in_tile: set[str] = set()
            for entry in bnd.entries:
                low = entry.name.lower()
                if low.endswith(".compendium"):
                    continue
                # Soulstruct's Elden Ring NVMHKT support is explicitly partial.
                # Probe each payload quietly: HKX.from_bytes() otherwise prints a
                # full traceback before re-raising even when we deliberately skip
                # an unsupported binder entry.
                try:
                    with _quiet_havok_parse():
                        hkx = self.NavmeshHKX.from_bytes(
                            _entry_bytes(bnd, entry, self.oodle), compendium=compendium)
                        mesh = hkx.get_simple_mesh()
                except self.TypeNotDefinedError as exc:
                    parse_errors += 1
                    missing = _missing_havok_types(exc) or ("<unknown>",)
                    missing_in_tile.update(missing)
                    for name in missing:
                        self.unsupported_types[name] = self.unsupported_types.get(name, 0) + 1
                    continue
                except Exception:
                    parse_errors += 1
                    continue
                if len(mesh.vertices) and mesh.faces:
                    meshes.append((np.asarray(mesh.vertices, dtype=np.float64), mesh.faces))

            if not meshes:
                if missing_in_tile:
                    self._note_unsupported_tile(map_id, tuple(missing_in_tile))
                    return None
                raise RuntimeError(
                    f"binder parsed but yielded no navmesh meshes ({parse_errors} entry parse failures)"
                )

            all_vertices = np.concatenate([v for v, _ in meshes], axis=0)
            ox, oz, frame = choose_world_offset(all_vertices, map_id)
            self.frames[map_id] = frame
            tris = []
            for vertices, faces in meshes:
                world = vertices.copy()
                world[:, 0] += ox
                world[:, 2] += oz
                tri = triangulate(world, faces)
                if len(tri):
                    tris.append(tri)
            if not tris:
                raise RuntimeError("navmesh meshes contained no usable top-down faces")
            self.successful_tiles += 1
            return Triangles.from_triangles(np.concatenate(tris, axis=0))
        except Exception as exc:
            self.errors[map_id] = f"{type(exc).__name__}: {exc}"
            return None

    def _candidate_tiles(self, area: int, world_x: float, world_z: float) -> Iterable[tuple[str, Triangles]]:
        # Prefer the finest tile. Parents are valid fallbacks for versions/maps
        # that keep navigation at a coarser LOD.
        seen = set()
        for tier in (0, 1, 2):
            map_id = map_id_for_world(area, world_x, world_z, tier)
            if map_id in seen:
                continue
            seen.add(map_id)
            mesh = self.get_tile(map_id)
            if mesh is not None:
                yield map_id, mesh

    def ray_heights(self, area: int, world_x: float, world_z: float) -> tuple[list[float], str | None]:
        """Return all ray hits from the finest available tile that covers X/Z."""
        for map_id, mesh in self._candidate_tiles(area, world_x, world_z):
            hits = mesh.ray_heights(world_x, world_z)
            if hits:
                return hits, map_id
        return [], None

    def report(self) -> dict:
        return {
            "disabledReason": self.disabled_reason,
            "successfulTiles": self.successful_tiles,
            "unsupportedTiles": self.unsupported_tiles,
            "unsupportedTypes": dict(self.unsupported_types),
            "tileFrames": self.frames,
            "tileErrors": self.errors,
        }


def robust_surface(source, area: int, world_x: float, world_z: float):
    """Return ``(surface_y, method, quality, tile)`` using neighbourhood layer consensus.

    A render mesh may contain a roof above the terrain and a cave below it. We
    therefore do not simply choose the highest centre hit. Every vertical layer
    is scored by how many nearby rays contain a compatible hit. Broad terrain
    wins over an isolated structure; if two layers have equal support, the
    higher one wins, preserving natural stacked topography.
    """
    prefix = getattr(source, "method_prefix", "navmesh")
    centre_hits, centre_tile = source.ray_heights(area, world_x, world_z)

    samples: list[tuple[float, list[float], str | None]] = [(0.0, centre_hits, centre_tile)]
    for radius in NEIGHBOUR_RINGS:
        for i in range(NEIGHBOUR_DIRECTIONS):
            angle = 2.0 * math.pi * i / NEIGHBOUR_DIRECTIONS
            x = world_x + math.cos(angle) * radius
            z = world_z + math.sin(angle) * radius
            hits, tile = source.ray_heights(area, x, z)
            if hits:
                samples.append((radius, hits, tile))

    populated = [sample for sample in samples if sample[1]]
    if not populated:
        return None

    # Candidate heights come from real ray intersections only. Deduplicate
    # coarsely to keep scoring bounded on complex stacked geometry.
    candidates: list[float] = []
    for _, hits, _ in populated:
        for y in hits:
            if not math.isfinite(y):
                continue
            if not any(abs(y - old) <= 0.75 for old in candidates):
                candidates.append(float(y))

    best = None
    for candidate in candidates:
        matched: list[tuple[float, float, str | None]] = []
        residual = 0.0
        for radius, hits, tile in populated:
            tolerance = LAYER_BASE_TOLERANCE + LAYER_SLOPE_TOLERANCE * radius
            nearest = min(hits, key=lambda h: abs(h - candidate))
            error = abs(nearest - candidate)
            if error <= tolerance:
                matched.append((radius, float(nearest), tile))
                residual += error / max(tolerance, 1e-6)
        support = len(matched)
        if not support:
            continue
        # Coverage dominates. Residual only breaks similar coverage, then the
        # higher layer wins ties (correct for broad natural stacked terrain).
        score = (support, -residual / support, candidate)
        if best is None or score > best[0]:
            best = (score, candidate, matched)

    if best is None:
        if centre_hits:
            return float(centre_hits[0]), prefix, "exact", centre_tile
        return None

    _, candidate, matched = best
    support = len(matched)
    required = min(MIN_LAYER_SUPPORT, max(3, math.ceil(len(populated) * 0.35)))

    if centre_hits:
        # Use the exact centre intersection belonging to the winning layer when
        # available. This preserves local slope instead of replacing it with a
        # neighbourhood median.
        centre_tol = LAYER_BASE_TOLERANCE
        centre_match = min(centre_hits, key=lambda h: abs(h - candidate))
        if abs(centre_match - candidate) <= centre_tol:
            is_top = abs(centre_match - centre_hits[0]) <= 0.20
            if support >= required and is_top:
                return float(centre_match), prefix, "exact", centre_tile
            if support >= required:
                return float(centre_match), f"{prefix}-neighborhood", "approx", centre_tile
        # If consensus is weak, centre top is safer than flattening a cliff.
        if support < required:
            return float(centre_hits[0]), prefix, "exact", centre_tile

    # No usable centre face or the consensus layer is inferred from neighbours.
    if support < 3:
        return None
    matched_y = [y for _, y, _ in matched]
    tile = centre_tile or next((t for _, _, t in matched if t), None)
    return float(median(matched_y)), f"{prefix}-neighborhood", "approx", tile


class SurfaceResolver:
    """Primary FLVER terrain with lazy NVMHKT fallback and final skip."""

    def __init__(self, game_dir: str, mod_dir: str | None, cache_size: int = 10):
        self.game_dir = game_dir
        self.mod_dir = mod_dir
        self.cache_size = cache_size
        self.flver: FLVERTerrainSource | None = None
        self.navmesh: NavmeshSource | None = None
        self.flver_init_error: str | None = None
        self.navmesh_init_error: str | None = None
        self.fallback_queries = 0
        self.fallback_resolved = 0
        try:
            self.flver = FLVERTerrainSource(game_dir, mod_dir, cache_size=min(cache_size, FLVER_TILE_CACHE))
        except Exception as exc:
            self.flver_init_error = f"{type(exc).__name__}: {exc}"
            print(f"WARNING: FLVER terrain provider unavailable: {self.flver_init_error}", flush=True)

    def _ensure_navmesh(self) -> NavmeshSource | None:
        if self.navmesh is not None:
            return self.navmesh
        if self.navmesh_init_error is not None:
            return None
        try:
            self.navmesh = NavmeshSource(self.game_dir, self.mod_dir, max(2, self.cache_size))
        except Exception as exc:
            self.navmesh_init_error = f"{type(exc).__name__}: {exc}"
            print(f"WARNING: NVMHKT fallback unavailable: {self.navmesh_init_error}", flush=True)
            return None
        return self.navmesh

    def surface(self, area: int, world_x: float, world_z: float):
        if self.flver is not None and not self.flver.disabled_reason:
            result = robust_surface(self.flver, area, world_x, world_z)
            if result is not None:
                return result

        self.fallback_queries += 1
        nav = self._ensure_navmesh()
        if nav is None or nav.disabled_reason:
            return None
        result = robust_surface(nav, area, world_x, world_z)
        if result is not None:
            self.fallback_resolved += 1
        return result

    @property
    def fully_disabled(self) -> bool:
        flver_disabled = self.flver is None or bool(self.flver.disabled_reason)
        nav = self.navmesh
        nav_disabled = self.navmesh_init_error is not None or (nav is not None and bool(nav.disabled_reason))
        # If fallback has not been initialized yet, it may still be usable.
        return flver_disabled and nav_disabled

    def close(self):
        if self.flver is not None:
            self.flver.close()
        if self.navmesh is not None:
            self.navmesh.close()

    def report(self) -> dict:
        return {
            "strategy": "flver-map-piece -> nvmhkt -> skip",
            "primary": self.flver.report() if self.flver is not None else {
                "disabledReason": self.flver_init_error or "not initialized"
            },
            "fallback": self.navmesh.report() if self.navmesh is not None else {
                "disabledReason": self.navmesh_init_error,
                "initialized": False,
            },
            "fallbackQueries": self.fallback_queries,
            "fallbackResolved": self.fallback_resolved,
        }

def marker_world(marker: dict) -> tuple[int, float, float] | None:
    if not isinstance(marker.get("h"), (int, float)):
        return None
    if not isinstance(marker.get("px"), (int, float)) or not isinstance(marker.get("py"), (int, float)):
        return None
    master = marker.get("master")
    if master not in {"M00", "M01", "M10"}:
        return None
    source_map = str(marker.get("map") or "").lower()
    if any(source_map.startswith(prefix) for prefix in DETACHED_LEGACY_PREFIXES):
        return None
    area = 61 if master == "M10" else 60
    world_x = float(marker["px"]) - OFFSET_X
    world_z = OFFSET_Y - float(marker["py"])
    return area, world_x, world_z


def clear_surface_fields(marker: dict) -> None:
    for key in ("surfaceH", "surfaceDelta", "surfaceMethod", "surfaceQuality", "surfaceTile"):
        marker.pop(key, None)


def annotate_documents(resolver, docs: list[tuple[Path, dict]], verbose=True) -> dict:
    refs: list[tuple[Path, dict]] = []
    for path, doc in docs:
        for marker in doc.get("markers", []):
            clear_surface_fields(marker)
            if marker_world(marker) is not None:
                refs.append((path, marker))

    # Spatial order keeps both MapPiece and NVMHKT tile LRUs hot.
    refs.sort(key=lambda pm: (
        pm[1].get("master", ""),
        math.floor((float(pm[1]["px"]) - OFFSET_X) / TILE_WORLD),
        math.floor((OFFSET_Y - float(pm[1]["py"])) / TILE_WORLD),
    ))

    stats = defaultdict(int)
    by_file = defaultdict(lambda: defaultdict(int))
    total = len(refs)
    for index, (path, marker) in enumerate(refs, 1):
        fully_disabled = getattr(resolver, "fully_disabled", None)
        if fully_disabled is None:
            fully_disabled = bool(getattr(resolver, "disabled_reason", None))
        if fully_disabled:
            # Both providers have established a systemic incompatibility. Skip
            # the remainder rather than repeating known failures per marker.
            for rem_path, _ in refs[index - 1:]:
                stats["unresolved"] += 1
                by_file[rem_path.name]["unresolved"] += 1
            break
        world = marker_world(marker)
        if world is None:
            continue
        area, world_x, world_z = world
        if hasattr(resolver, "surface"):
            result = resolver.surface(area, world_x, world_z)
        else:  # small test doubles / backwards-compatible unit use
            result = robust_surface(resolver, area, world_x, world_z)
        if result is None:
            stats["unresolved"] += 1
            by_file[path.name]["unresolved"] += 1
            continue
        surface_y, method, quality, tile = result
        delta = float(marker["h"]) - surface_y
        marker["surfaceH"] = round(surface_y, 1)
        marker["surfaceDelta"] = round(delta, 1)
        marker["surfaceMethod"] = method
        marker["surfaceQuality"] = quality
        if tile:
            marker["surfaceTile"] = tile
        stats[method] += 1
        by_file[path.name][method] += 1
        if verbose and (index % 100 == 0 or index == total):
            flver_count = stats.get("flver", 0) + stats.get("flver-neighborhood", 0)
            nav_count = stats.get("navmesh", 0) + stats.get("navmesh-neighborhood", 0)
            print(
                f"  surface rays: {index:,}/{total:,} | FLVER {flver_count:,} | "
                f"NVMHKT fallback {nav_count:,} | unresolved {stats.get('unresolved', 0):,}",
                flush=True,
            )

    report = {
        "total": total,
        "stats": dict(stats),
        "files": {k: dict(v) for k, v in by_file.items()},
    }
    if hasattr(resolver, "report"):
        report["providers"] = resolver.report()
    elif hasattr(resolver, "disabled_reason"):
        # Backward-compatible diagnostic shape for tests/older callers that
        # pass one raw provider instead of SurfaceResolver.
        report["parser"] = {
            "disabledReason": getattr(resolver, "disabled_reason", None),
            "successfulTiles": getattr(resolver, "successful_tiles", 0),
            "unsupportedTiles": getattr(resolver, "unsupported_tiles", 0),
            "unsupportedTypes": dict(getattr(resolver, "unsupported_types", {})),
        }
    return report

def load_documents(data_dir: Path) -> list[tuple[Path, dict]]:
    docs = []
    for name in MARKER_FILES:
        path = data_dir / name
        if not path.is_file():
            continue
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            print(f"  {name}: skipped, invalid JSON: {exc}")
            continue
        if not isinstance(doc, dict) or not isinstance(doc.get("markers", []), list):
            print(f"  {name}: skipped, no marker list")
            continue
        docs.append((path, doc))
    return docs


def write_documents(docs: list[tuple[Path, dict]]) -> None:
    for path, doc in docs:
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, path)


def parse_args():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--game-dir", help="ELDEN RING/Game folder (auto-detected if omitted)")
    p.add_argument("--mod-dir", help="optional loose-file mod directory")
    p.add_argument("--data-dir", default=str(ROOT / "data"), help="generated marker JSON directory")
    p.add_argument("--cache-size", type=int, default=10, help="surface tile LRU size")
    return p.parse_args()


def main():
    args = parse_args()
    if sys.version_info < (3, 13):
        raise SystemExit(f"surface-height scan requires Python 3.13+; found {sys.version.split()[0]}")
    from erlib.gamepath import require_game_dir
    import erlib.modfiles as modfiles
    game_dir = require_game_dir(args.game_dir)
    mod_dir = modfiles.find_mod_dir(args.mod_dir)
    docs = load_documents(Path(args.data_dir))
    if not docs:
        raise SystemExit("no generated marker JSON files found; run the normal marker extractors first")

    print(
        "surface-height scan: MapPiece FLVER geometry (primary) -> "
        "NVMHKT hk2018 (fallback) -> safe skip ...",
        flush=True,
    )
    resolver = SurfaceResolver(game_dir, mod_dir, max(2, args.cache_size))
    try:
        report = annotate_documents(resolver, docs)
    finally:
        resolver.close()

    report_path = ROOT / "cache" / "surface-height-report.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    stats = report["stats"]
    flver_exact = stats.get("flver", 0)
    flver_approx = stats.get("flver-neighborhood", 0)
    nav_exact = stats.get("navmesh", 0)
    nav_approx = stats.get("navmesh-neighborhood", 0)
    unresolved = stats.get("unresolved", 0)
    resolved = flver_exact + flver_approx + nav_exact + nav_approx

    if report["total"] and resolved == 0:
        # Surface height is an enhancement, never a prerequisite for entering
        # the application. Preserve any previous annotations rather than
        # publishing an all-empty pass.
        print(
            "WARNING: no reliable surface geometry could be resolved. "
            "Surface-height enhancement was skipped; map/quests/catalog remain valid. "
            f"See {report_path}",
            flush=True,
        )
        return

    if report["total"] and resolved / report["total"] < 0.25:
        print(
            f"WARNING: only {resolved:,}/{report['total']:,} markers received a reliable "
            f"surface height; unresolved markers remain unannotated. See {report_path}",
            flush=True,
        )

    write_documents(docs)
    print(
        f"  annotated: {resolved:,}/{report['total']:,} | "
        f"FLVER {flver_exact + flver_approx:,} "
        f"(exact {flver_exact:,}, neighbourhood {flver_approx:,}) | "
        f"NVMHKT fallback {nav_exact + nav_approx:,} "
        f"(exact {nav_exact:,}, neighbourhood {nav_approx:,}) | "
        f"unresolved {unresolved:,}",
        flush=True,
    )
    print(f"-> {report_path}")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        raise SystemExit(130)
    except Exception:
        traceback.print_exc()
        raise SystemExit(1)
