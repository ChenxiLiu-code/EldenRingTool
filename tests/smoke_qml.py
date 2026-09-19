"""Offscreen QML construction smoke test. Requires PySide6."""
import os
import sys
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pathlib import Path
from PySide6.QtCore import QUrl, QTimer
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuickControls2 import QQuickStyle

from eldenringtool.backend import Backend

QQuickStyle.setStyle("Basic")
app = QGuiApplication(sys.argv)
engine = QQmlApplicationEngine()
backend = Backend()
engine.rootContext().setContextProperty("backend", backend)
qml = Path(__file__).resolve().parents[1] / "eldenringtool" / "qml" / "Main.qml"
engine.load(QUrl.fromLocalFile(str(qml)))
if not engine.rootObjects():
    raise SystemExit("QML failed to construct")
QTimer.singleShot(100, app.quit)
result = app.exec()
backend.shutdown()
from shiboken6 import delete
delete(engine)
raise SystemExit(result)
