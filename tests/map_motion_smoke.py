"""Exercise map motion with the installed marker corpus, without reading saves."""
import os
import sys
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Event, Thread
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
os.environ.setdefault('QT_QUICK_BACKEND', 'software')

from PySide6.QtCore import QObject, QPoint, QPointF, Qt, QUrl, Slot, qInstallMessageHandler
from PySide6.QtGui import QGuiApplication, QWheelEvent, QFontDatabase, QFont
from PySide6.QtQml import QQmlApplicationEngine, QQmlExpression, QQmlEngine
from PySide6.QtQuickControls2 import QQuickStyle
from PySide6.QtTest import QTest
from eldenringtool.backend import Backend, ROOT, DATA, ASSETS
from eldenringtool.core.state_store import StateStore


class MeasuredBackend(Backend):
    queries = 0

    @Slot(str, float, float, float, float, float, str, str, bool, result='QVariantList')
    def visibleMarkers(self, *args):
        self.queries += 1
        return super().visibleMarkers(*args)


QQuickStyle.setStyle('Basic')
app = QGuiApplication(sys.argv)
if os.name == 'nt':
    for name in ('msyh.ttc', 'seguisym.ttf'):
        QFontDatabase.addApplicationFont(str(Path(os.environ.get('WINDIR', 'C:/Windows')) / 'Fonts' / name))
    app.setFont(QFont('Microsoft YaHei'))
messages = []
qInstallMessageHandler(lambda kind, context, text: messages.append(text))
with TemporaryDirectory(prefix='motion-', dir=ROOT / 'cache') as directory:
    with patch('eldenringtool.backend.validate_cache', return_value=SimpleNamespace(valid=False, reason='', game_dir='')), patch('eldenringtool.backend.recover_interrupted_scan'):
        backend = MeasuredBackend()
    backend.timer.stop()
    backend.store = StateStore(Path(directory) / 'state.json')
    backend._setup = False
    for name in ('markers', 'items', 'unique_drops', 'mausoleums', 'pieces'):
        path = DATA / f'{name}.json'
        if path.exists():
            backend.markers.extend(json.loads(path.read_text(encoding='utf-8')).get('markers', []))
    backend.marker_by_id = {str(m['id']): m for m in backend.markers}
    for marker in backend.markers:
        marker['_uiIcon'] = backend._icon_name(marker.get('icon'))
    manifest = ASSETS / 'tiles' / 'manifest.json'
    if manifest.exists():
        backend.tile_manifest = json.loads(manifest.read_text(encoding='utf-8'))
    engine = QQmlApplicationEngine()
    engine.rootContext().setContextProperty('backend', backend)
    engine.load(QUrl.fromLocalFile(str(ROOT / 'eldenringtool/qml/Main.qml')))
    assert engine.rootObjects(), messages
    window = engine.rootObjects()[0]
    QTest.qWait(700)
    scene = window.findChild(QObject, 'mapRoot')
    viewport = window.findChild(QObject, 'mapViewport')
    point = scene.mapToScene(QPointF(scene.width() / 2, scene.height() / 2))
    initial_queries = backend.queries
    initial_render_zoom = scene.property('renderZoom')
    for _ in range(12):
        app.sendEvent(window, QWheelEvent(point, point, QPoint(), QPoint(0, 120), Qt.NoButton, Qt.NoModifier, Qt.NoScrollPhase, False))
        QTest.qWait(24)
        assert scene.property('renderZoom') == initial_render_zoom
        assert backend.queries == initial_queries, 'Rebuilding markers during zoom'
    QTest.qWait(400)
    assert backend.queries > initial_queries
    assert abs(scene.property('renderZoom') - scene.property('mapZoom')) < 1e-6
    initial_queries = backend.queries
    QTest.mousePress(window, Qt.LeftButton, Qt.NoModifier, point.toPoint())
    for i in range(1, 11):
        QTest.mouseMove(window, point.toPoint() + QPoint(i * 20, i * 5), 25)
    assert backend.queries == initial_queries, 'Rebuilding markers during drag'
    QTest.mouseRelease(window, Qt.LeftButton, Qt.NoModifier, point.toPoint() + QPoint(200, 50))
    released_x = viewport.property('contentX')
    QTest.qWait(120)
    assert abs(viewport.property('contentX') - released_x) > 1
    assert backend.queries == initial_queries, 'Rebuilding markers during inertia'
    QTest.qWait(500)
    assert backend.queries > initial_queries
    # Hold a replacement image in flight to expose the old remove-before-load
    # flash deterministically, including a second request while loading.
    def map_tiles(item):
        result = []
        for child in item.childItems():
            if child.objectName() == 'mapTile':
                result.append(child)
            result.extend(map_tiles(child))
        return result

    displayed = [t for t in map_tiles(scene) if t.property('visible')]
    assert displayed, 'Real map tiles must be loaded for the handoff test'
    image_bytes = Path(displayed[0].property('source').toLocalFile()).read_bytes()
    release = Event()

    class DelayedTile(BaseHTTPRequestHandler):
        def do_GET(self):
            release.wait(5)
            self.send_response(200)
            self.send_header('Content-Type', 'image/webp')
            self.end_headers()
            try:
                self.wfile.write(image_bytes)
            except ConnectionError:
                pass  # Superseded image requests may be cancelled by Qt.

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(('127.0.0.1', 0), DelayedTile)
    server_thread = Thread(target=server.serve_forever, daemon=True)
    server_thread.start()
    try:
        def stage_test_tile(suffix):
            rows = [{'source': f'http://127.0.0.1:{server.server_port}/{suffix}.webp',
                     'x': 0, 'y': 0, 'size': 256}]
            expression = QQmlExpression(QQmlEngine.contextForObject(scene), scene,
                                       f'stageTiles({json.dumps(rows)})')
            expression.evaluate()
            assert not expression.hasError(), expression.error().toString()

        def map_frame():
            origin = scene.mapToScene(QPointF(0, 0)).toPoint()
            # Exclude the bottom status label, which reports pending tile count.
            return window.grabWindow().copy(origin.x(), origin.y(),
                                            int(scene.width()), int(scene.height()) - 50)

        before_handoff = map_frame()
        assert not before_handoff.isNull()
        stage_test_tile('first')
        QTest.qWait(100)
        assert map_frame() == before_handoff, 'Map frame changed before replacement loaded'
        stage_test_tile('latest')
        QTest.qWait(100)
        assert map_frame() == before_handoff, 'Superseded request changed the displayed frame'
        assert scene.property('tilesPending')
        assert all(t.property('visible') for t in displayed), 'Old mip disappeared while loading'
        release.set()
        for _ in range(100):
            QTest.qWait(20)
            if not scene.property('tilesPending'):
                break
        assert not scene.property('tilesPending'), 'Replacement batch never committed'
        active = [t for t in map_tiles(scene) if t.property('visible')]
        assert len(active) == 1 and active[0].property('source').toString().endswith('/latest.webp')
    finally:
        release.set()
        server.shutdown()
        server.server_close()
        server_thread.join()
    nav = window.findChild(QObject, 'mainNav')
    nav.setProperty('currentIndex', 3)
    QTest.qWait(200)
    poll = window.findChild(QObject, 'savePollIntervalInput')
    poll.forceActiveFocus()
    QTest.keyClick(window, Qt.Key_A, Qt.ControlModifier)
    for key in (Qt.Key_5, Qt.Key_Period, Qt.Key_0):
        QTest.keyClick(window, key)
    QTest.keyClick(window, Qt.Key_Return)
    assert backend.savePollInterval == 5.0
    assert backend.timer.interval() == 5000
    if '--screenshots' in sys.argv:
        window.setWidth(1120)
        window.setHeight(700)
        QTest.qWait(200)
        window.grabWindow().save(str(ROOT / 'cache/poll-settings.png'))
    backend.shutdown()
    from shiboken6 import delete
    delete(engine)
    errors = [m for m in messages if any(word in m for word in ('Error', 'Binding loop', "Can't", 'different type'))]
    assert not errors, errors
    print(f'MOTION PASS: {len(backend.markers)} source markers; no marker rebuilds during zoom, drag or inertia; delayed tile handoff and superseded requests passed; polling control applied')
