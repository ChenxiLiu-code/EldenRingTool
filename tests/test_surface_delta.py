import importlib.util
import sys
import unittest
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "tools" / "annotate_surface_delta.py"
spec = importlib.util.spec_from_file_location("surface_delta", MODULE)
surface = importlib.util.module_from_spec(spec)
sys.modules["surface_delta"] = surface
assert spec.loader is not None
spec.loader.exec_module(surface)


class SurfaceGeometryTests(unittest.TestCase):
    def test_vertical_ray_on_quad(self):
        verts = np.array([[0, 100, 0], [100, 100, 0], [100, 100, 100], [0, 100, 100]], float)
        mesh = surface.Triangles.from_triangles(surface.triangulate(verts, [[0, 1, 2, 3]]))
        self.assertEqual(mesh.ray_heights(50, 50), [100.0])

    def test_stacked_layers_return_top_first(self):
        top = np.array([[0, 100, 0], [100, 100, 0], [100, 100, 100], [0, 100, 100]], float)
        verts = np.vstack([top, top + np.array([0, -50, 0])])
        mesh = surface.Triangles.from_triangles(
            surface.triangulate(verts, [[0, 1, 2, 3], [4, 5, 6, 7]])
        )
        self.assertEqual(mesh.ray_heights(50, 50), [100.0, 50.0])

    def test_coordinate_frame_detection(self):
        local = np.array([[-128, 0, -128], [128, 0, -128], [128, 0, 128], [-128, 0, 128]], float)
        self.assertEqual(surface.choose_world_offset(local, "m60_42_36_00")[2], "center-local")
        corner = np.array([[0, 0, 0], [256, 0, 0], [256, 0, 256], [0, 0, 256]], float)
        self.assertEqual(surface.choose_world_offset(corner, "m60_42_36_00")[2], "corner-local")
        world = corner.copy()
        world[:, 0] += 42 * 256
        world[:, 2] += 36 * 256
        self.assertEqual(surface.choose_world_offset(world, "m60_42_36_00")[2], "world")

    def test_isolated_high_structure_is_rejected(self):
        class Fake:
            def ray_heights(self, area, x, z):
                if abs(x) < 1e-6 and abs(z) < 1e-6:
                    return [125.0], "m60_00_00_00"
                return [100.0], "m60_00_00_00"

        result = surface.robust_surface(Fake(), 60, 0.0, 0.0)
        self.assertIsNotNone(result)
        self.assertAlmostEqual(result[0], 100.0)
        self.assertEqual(result[1], "navmesh-neighborhood")

    def test_archive_path_candidates_cover_retail_and_loose_layouts(self):
        source = object.__new__(surface.NavmeshSource)
        self.assertEqual(
            source._paths("m60_42_36_00"),
            (
                "/map/m60/m60_42_36_00/m60_42_36_00.nvmhktbnd.dcx",
                "/map/m60_42_36_00/m60_42_36_00.nvmhktbnd.dcx",
            ),
        )
        self.assertEqual(
            source._paths("m61_45_42_00")[0],
            "/map/m61/m61_45_42_00/m61_45_42_00.nvmhktbnd.dcx",
        )

    def test_natural_stacked_top_layer_is_kept(self):
        class Fake:
            def ray_heights(self, area, x, z):
                return [300.0, 100.0], "m60_00_00_00"

        result = surface.robust_surface(Fake(), 60, 0.0, 0.0)
        self.assertIsNotNone(result)
        self.assertEqual(result[0], 300.0)
        self.assertEqual(result[1], "navmesh")


if __name__ == "__main__":
    unittest.main()


def test_missing_havok_type_extraction():
    exc = RuntimeError("Type hkdStaticAabbTree is not defined in Havok module hk2018.")
    assert surface._missing_havok_types(exc) == ("hkdStaticAabbTree",)
    exc2 = RuntimeError("Unknown Havok types in file. Types:['hkdA', 'hkdB']")
    assert surface._missing_havok_types(exc2) == ("hkdA", "hkdB")


def test_disabled_parser_fast_forwards_remaining_markers(tmp_path):
    class FakeSource:
        def __init__(self):
            self.disabled_reason = None
            self.successful_tiles = 0
            self.unsupported_tiles = 0
            self.unsupported_types = {}
            self.calls = 0
        def ray_heights(self, area, x, z):
            self.calls += 1
            self.disabled_reason = "unsupported"
            return [], None

    source = FakeSource()
    markers = [
        {"px": 0.0, "py": 0.0, "h": 10, "master": "M00", "map": "m10_00_00_00"}
        for _ in range(20)
    ]
    report = surface.annotate_documents(source, [(tmp_path / "markers.json", {"markers": markers})], verbose=False)
    assert report["stats"]["unresolved"] == 20
    # robust_surface makes center + neighbour calls only for the first marker;
    # the other 19 are fast-forwarded without further resource parsing.
    assert source.calls <= 1 + len(surface.NEIGHBOUR_RINGS) * surface.NEIGHBOUR_DIRECTIONS
    assert report["parser"]["disabledReason"] == "unsupported"


def test_havok_incompatibility_circuit_breaker_after_three_tiles(capsys):
    source = object.__new__(surface.NavmeshSource)
    source.successful_tiles = 0
    source.unsupported_tiles = 0
    source.unsupported_tile_ids = set()
    source.unsupported_types = {}
    source.errors = {}
    source.disabled_reason = None
    source._note_unsupported_tile("m60_01_01_00", ("hkdStaticAabbTree",))
    source._note_unsupported_tile("m60_01_02_00", ("hkdStaticAabbTree",))
    assert source.disabled_reason is None
    source._note_unsupported_tile("m60_01_03_00", ("hkdStaticAabbTree",))
    assert "hkdStaticAabbTree" in source.disabled_reason
    assert source.unsupported_tiles == 3
    assert "surface-height enhancement will be skipped" in capsys.readouterr().out


def test_flver_part_transform_uses_tile_center_and_xzy_rotation():
    tri = np.array([[[0, 0, 0], [1, 0, 0], [0, 0, 1]]], dtype=float)
    world = surface._apply_part_transform(
        tri, translate=(0, 100, 0), rotate=(0, 0, 0), scale=(1, 1, 1), map_id="m60_42_36_00"
    )
    assert np.allclose(world[0, 0], [42 * 256 + 128, 100, 36 * 256 + 128])

    rotated = surface._apply_part_transform(
        tri, translate=(0, 0, 0), rotate=(0, 0, 90), scale=(1, 1, 1), map_id="m60_00_00_00"
    )
    # FromSoftware XZY order: with only Z rotation, +X rotates to +Y.
    assert np.allclose(rotated[0, 1] - rotated[0, 0], [0, 1, 0], atol=1e-5)


def test_flver_model_paths_cover_native_retail_and_flattened_layouts():
    paths = surface.FLVERTerrainSource._model_paths("m60_42_36_00", "m60_42_36_00_0000")
    assert paths[0] == "/map/m60_42_36_00/m60_42_36_00_0000.flver.dcx"
    assert "/map/m60/m60_42_36_00/m60_42_36_00_0000.flver.dcx" in paths
    assert "/map/m60/m60_42_36_00_0000.flver" in paths
    assert "/map/m60_42_36_00_0000.flver.dcx" in paths

    # Extension-bearing model names must be normalized exactly once.
    with_ext = surface.FLVERTerrainSource._model_paths(
        "m60_42_36_00", "m60_42_36_00_0000.flver.dcx"
    )
    assert all(".flver.flver" not in p and ".dcx.flver" not in p for p in with_ext)
    assert with_ext[0].endswith("/m60_42_36_00_0000.flver.dcx")


def test_flver_fine_neighbors_cover_tile_seams():
    ids = surface.FLVERTerrainSource._fine_neighbor_ids(60, 42 * 256 + 128, 36 * 256 + 128)
    assert "m60_41_36_00" in ids
    assert "m60_43_36_00" in ids
    assert "m60_42_35_00" in ids
    assert "m60_42_37_00" in ids
    assert len(ids) == 8


def test_flver_layer_consensus_rejects_local_roof():
    class Fake:
        method_prefix = "flver"
        def ray_heights(self, area, x, z):
            radius = (x * x + z * z) ** 0.5
            if radius <= 20:
                return [130.0, 100.0], "m60_00_00_00"
            return [100.0], "m60_00_00_00"

    result = surface.robust_surface(Fake(), 60, 0.0, 0.0)
    assert result is not None
    assert abs(result[0] - 100.0) < 1e-6
    assert result[1] == "flver-neighborhood"


def test_surface_resolver_uses_navmesh_only_after_flver_miss():
    class EmptyFLVER:
        method_prefix = "flver"
        disabled_reason = None
        def ray_heights(self, area, x, z):
            return [], None

    class GoodNav:
        method_prefix = "navmesh"
        disabled_reason = None
        def ray_heights(self, area, x, z):
            return [90.0], "m60_00_00_00"

    resolver = object.__new__(surface.SurfaceResolver)
    resolver.game_dir = ""
    resolver.mod_dir = None
    resolver.cache_size = 2
    resolver.flver = EmptyFLVER()
    resolver.navmesh = GoodNav()
    resolver.flver_init_error = None
    resolver.navmesh_init_error = None
    resolver.fallback_queries = 0
    resolver.fallback_resolved = 0
    result = resolver.surface(60, 0.0, 0.0)
    assert result is not None and result[1] == "navmesh"
    assert resolver.fallback_queries == 1
    assert resolver.fallback_resolved == 1
