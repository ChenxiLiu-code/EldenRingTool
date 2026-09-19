"""Small standard-library bootstrap for the Windows launcher.

PySide6 is the GUI runtime itself, so it cannot be installed from inside a QML
window that does not exist yet. The launcher installs only PySide6 when absent;
all parser/extractor dependencies are checked and, when needed, installed from
the first-run parsing screen with visible logs.
"""
from __future__ import annotations

import importlib.util
import subprocess
import sys


def ensure_python() -> None:
    if sys.version_info < (3, 13):
        raise SystemExit(
            f"EldenRingTool requires Python 3.13 or newer; current interpreter is {sys.version.split()[0]}."
        )


def ensure_pyside() -> None:
    try:
        ready = importlib.util.find_spec("PySide6.QtCore") is not None
    except (ImportError, ModuleNotFoundError, AttributeError, ValueError):
        ready = False
    if ready:
        return
    print("PySide6 is not installed. Installing the EldenRingTool GUI runtime...")
    subprocess.check_call([
        sys.executable, "-m", "pip", "install", "--disable-pip-version-check", "--no-input", "PySide6>=6.8,<7"
    ])


def main() -> int:
    ensure_python()
    ensure_pyside()
    from eldenringtool.app import main as app_main
    return int(app_main())


if __name__ == "__main__":
    raise SystemExit(main())
