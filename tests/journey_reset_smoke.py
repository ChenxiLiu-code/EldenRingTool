"""Exercise the confirmation dialog using an isolated state file."""
import os
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
os.environ['QT_QUICK_BACKEND'] = 'software'
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch
from PySide6.QtCore import QObject, QUrl, QPointF, Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuickControls2 import QQuickStyle
from PySide6.QtTest import QTest
from eldenringtool.backend import Backend
from eldenringtool.core.state_store import StateStore

QQuickStyle.setStyle('Basic')
app = QGuiApplication([])
with TemporaryDirectory(dir='cache', prefix='journey-ui-') as folder:
    with patch('eldenringtool.backend.validate_cache', return_value=SimpleNamespace(valid=False, reason='', game_dir='')), patch('eldenringtool.backend.recover_interrupted_scan'):
        backend = Backend()
    backend.timer.stop()
    backend._setup = False
    backend.store = StateStore(Path(folder) / 'state.json')
    backend.save_path = 'test-account/save.sl2'
    hero = {'slot': 0, 'name': '测试角色', 'ok': True, '_flags': {}}
    backend.characters = [hero]
    backend.active_slot = 0
    backend.quest_doc = {'quests': []}
    backend.setMarkerChecked('manual', True)
    engine = QQmlApplicationEngine()
    engine.rootContext().setContextProperty('backend', backend)
    engine.load(QUrl.fromLocalFile(str(Path('eldenringtool/qml/Main.qml').resolve())))
    assert engine.rootObjects(), 'QML failed to load'
    window = engine.rootObjects()[0]
    QTest.qWait(150)
    window.findChild(QObject, 'mainNav').setProperty('currentIndex', 3)
    QTest.qWait(150)
    button = window.findChild(QObject, 'journeyResetButton')
    dialog = window.findChild(QObject, 'journeyResetDialog')
    assert button and button.property('enabled')
    button.clicked.emit()
    QTest.qWait(150)
    assert dialog.property('visible')
    assert backend.store.marker_checked(backend.save_path, hero, 'manual')

    def click(name):
        item = window.findChild(QObject, name)
        point = item.mapToScene(QPointF(item.width() / 2, item.height() / 2)).toPoint()
        QTest.mouseClick(window, Qt.LeftButton, Qt.NoModifier, point)
        QTest.qWait(150)

    click('journeyResetCancel')
    assert not dialog.property('visible')
    assert backend.store.marker_checked(backend.save_path, hero, 'manual')
    button.clicked.emit()
    QTest.qWait(150)
    click('journeyResetConfirm')
    assert not dialog.property('visible')
    assert not backend.store.marker_checked(backend.save_path, hero, 'manual')
    backend.shutdown()
    window.close()
    engine.deleteLater()
    QTest.qWait(50)
print('Journey reset: open, cancel, confirm passed')
