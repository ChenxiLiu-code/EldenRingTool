from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QUrl
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuickControls2 import QQuickStyle

from .backend import Backend


def main() -> int:
    # Force the same Qt Quick Controls baseline on Windows/Linux instead of
    # inheriting native platform button colors (the Windows style can render
    # light buttons inside an otherwise dark QML window).
    QQuickStyle.setStyle("Basic")

    app = QGuiApplication(sys.argv)
    app.setApplicationName("EldenRingTool")
    app.setApplicationDisplayName("EldenRingTool")
    app.setOrganizationName("EldenRingTool")

    engine = QQmlApplicationEngine()
    backend = Backend()
    app.aboutToQuit.connect(backend.shutdown)
    engine.rootContext().setContextProperty("backend", backend)
    qml = Path(__file__).resolve().parent / "qml" / "Main.qml"
    engine.load(QUrl.fromLocalFile(str(qml)))
    if not engine.rootObjects():
        return 2
    result = app.exec()
    from shiboken6 import delete
    delete(engine)
    return result


if __name__ == "__main__":
    raise SystemExit(main())
