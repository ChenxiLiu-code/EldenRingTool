from pathlib import Path
import re
import pytest

from eldenringtool.core import scanner
from eldenringtool.core.resource_cache import manifest_path

ROOT = Path(__file__).resolve().parents[1]


def test_scan_rejects_resource_change_before_success_manifest(tmp_path, monkeypatch):
    gd = tmp_path / "Game"; gd.mkdir()
    (gd / "eldenring.exe").write_bytes(b"exe")
    (gd / "regulation.bin").write_bytes(b"reg")
    root = tmp_path / "app"; root.mkdir()
    (root / "requirements.txt").write_text("")
    monkeypatch.setattr(scanner, "missing_dependencies", lambda: [])
    monkeypatch.setattr(scanner, "build_steps", lambda *args, **kwargs: [])
    calls = iter([
        {"eldenring.exe": {"size": 3, "sha256": "a"}, "regulation.bin": {"size": 3, "sha256": "b"}},
        {"eldenring.exe": {"size": 4, "sha256": "changed"}, "regulation.bin": {"size": 3, "sha256": "b"}},
    ])
    monkeypatch.setattr(scanner, "_game_signatures", lambda _gd: next(calls))
    with pytest.raises(RuntimeError, match="解析期间游戏资源发生变化"):
        scanner.run_scan(root, str(gd))
    assert not manifest_path(root).exists()


def test_qml_four_page_and_native_map_contracts():
    text = (ROOT / "eldenringtool" / "qml" / "Main.qml").read_text(encoding="utf-8")
    for page in ("地图", "任务", "图鉴", "设置"):
        assert f'AppTabButton {{ text: "{page}" }}' in text
    assert "backend.visibleMarkers(master, mapZoom" in text
    assert "cache: true" in text
    assert "event.position" not in text
    assert "DragHandler" in text
    assert "modelData.cluster" in text
    assert "surfaceDelta" not in text
    assert "importLegacyMarkerChecks" in text
    # Top-level signal handlers dispatch through the active Loader instance;
    # they do not reach into ids living inside Component bodies.
    assert "rootLoader.item.refreshData" in text
    assert "rootLoader.item.appendLog" in text


def test_explicit_dark_control_contract_and_brand_rename():
    qml = (ROOT / "eldenringtool" / "qml" / "Main.qml").read_text(encoding="utf-8")
    app = (ROOT / "eldenringtool" / "app.py").read_text(encoding="utf-8")
    project = (ROOT / "pyproject.toml").read_text(encoding="utf-8")

    assert "EldenRingTool" in qml
    assert "EldenMap" not in qml
    assert 'QQuickStyle.setStyle("Basic")' in app
    assert 'name = "eldenringtool"' in project
    assert 'eldenringtool = "eldenringtool.app:main"' in project

    for component in ("AppButton", "AppField", "AppCheckBox", "AppComboBox", "AppTabButton"):
        assert f"component {component}:" in qml

    # All user-facing controls in the UI use the explicit dark components.
    # The only raw controls allowed are their inline component base types.
    stripped = re.sub(r"component AppButton: Button ", "", qml)
    stripped = re.sub(r"component AppField: TextField ", "", stripped)
    stripped = re.sub(r"component AppCheckBox: CheckBox ", "", stripped)
    stripped = re.sub(r"component AppComboBox: ComboBox ", "", stripped)
    stripped = re.sub(r"component AppTabButton: TabButton ", "", stripped)
    stripped = re.sub(r"component AppProgressBar: ProgressBar ", "", stripped)
    stripped = re.sub(r"component AppTextArea: TextArea ", "", stripped)
    assert not re.search(r"(?m)^\s*(Button|TextField|CheckBox|ComboBox|TabButton|ProgressBar|TextArea)\s*\{", stripped)


def test_runtime_hardening_contracts(tmp_path):
    backend = (ROOT / "eldenringtool" / "backend.py").read_text(encoding="utf-8")
    app = (ROOT / "eldenringtool" / "app.py").read_text(encoding="utf-8")
    from eldenringtool.core.state_store import StateStore
    state_path = tmp_path / "data" / "user-state.json"
    doc = StateStore(state_path).data
    assert not state_path.exists()
    assert all(doc.get(k) == {} for k in ("checked", "characterChecked", "questChecked", "slots", "settings"))
    assert "except InterruptedError as exc" in backend
    assert "worker.cancelled.connect(self._on_scan_cancelled)" in backend
    assert "math.isfinite(x)" in backend and "math.isfinite(y)" in backend
    assert "app.aboutToQuit.connect(backend.shutdown)" in app



def test_all_qml_backend_references_exist():
    import ast
    qml = (ROOT / "eldenringtool" / "qml" / "Main.qml").read_text(encoding="utf-8")
    backend_src = (ROOT / "eldenringtool" / "backend.py").read_text(encoding="utf-8")
    refs = set(re.findall(r"\bbackend\.([A-Za-z_]\w*)", qml))
    tree = ast.parse(backend_src)
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "Backend")
    names = {n.name for n in cls.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
    for node in cls.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    names.add(target.id)
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            names.add(node.target.id)
    assert refs <= names, f"QML references missing Backend members: {sorted(refs - names)}"


def test_scan_children_are_unbuffered_and_unique_drop_has_live_progress():
    steps = scanner.build_steps(ROOT, Path("/fake/Game"))
    assert steps and all(step.argv[1] == "-u" for step in steps)
    scan_src = (ROOT / "eldenringtool" / "core" / "scanner.py").read_text(encoding="utf-8")
    unique_src = (ROOT / "tools" / "extract_unique_drops.py").read_text(encoding="utf-8")
    assert "PYTHONUNBUFFERED" in scan_src
    assert "仍在执行" in scan_src
    assert "line_buffering=True" in unique_src
    assert "npc_drop_cache" in unique_src and "lot_chain_cache" in unique_src
    assert "MSB {i + 1}" in unique_src and "EMEVD {event_i}" in unique_src


def test_msb_reader_exposes_lazy_entry_name_helper():
    src = (ROOT / "tools" / "erlib" / "msb.py").read_text(encoding="utf-8")
    assert "def entry_name(self, off)" in src
    assert "out.append((off, self.entry_name(off)))" in src


def test_surface_height_step_is_disabled():
    from eldenringtool.core import scanner
    steps = scanner.build_steps(ROOT, Path('/fake/Game'))
    assert not any('annotate_surface_delta.py' in ' '.join(s.argv) for s in steps)
