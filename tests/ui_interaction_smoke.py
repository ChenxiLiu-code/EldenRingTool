import os,sys,json
os.environ['QT_QPA_PLATFORM']='offscreen'
os.environ['QT_QUICK_BACKEND']='software'
from pathlib import Path
from PySide6.QtCore import QUrl,QTimer,QObject,QPoint,QPointF,Qt,qInstallMessageHandler
from PySide6.QtGui import QGuiApplication,QWheelEvent,QFontDatabase,QFont
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtTest import QTest
from PySide6.QtQuickControls2 import QQuickStyle
from eldenringtool.backend import Backend,DATA
from eldenringtool.core.quest_engine import evaluate_document
from types import SimpleNamespace
from unittest.mock import patch
from tempfile import TemporaryDirectory
from eldenringtool.core.state_store import StateStore
state_dir = TemporaryDirectory(prefix='map-ui-', dir=DATA.parent/'cache')
QQuickStyle.setStyle('Basic'); app=QGuiApplication(sys.argv)
if os.name == 'nt':
 for filename in ('msyh.ttc', 'seguisym.ttf'):
  QFontDatabase.addApplicationFont(str(Path(os.environ.get('WINDIR', 'C:/Windows'))/'Fonts'/filename))
 app.setFont(QFont('Microsoft YaHei'))
with patch('eldenringtool.backend.validate_cache', return_value=SimpleNamespace(valid=False, reason='', game_dir='')), patch('eldenringtool.backend.recover_interrupted_scan'):
 b=Backend()
b.timer.stop(); b._setup=False
b.store = StateStore(Path(state_dir.name)/'state.json')
b.quest_doc={'quests':[]}
for pack,fn in [('base','base_game'),('dlc','dlc')]:
 for q in json.loads((DATA/'quests'/f'{fn}.json').read_text(encoding='utf-8'))['quests']: b.quest_doc['quests'].append({**q,'pack':pack})
b.quest_doc['quests'].extend(json.loads((DATA/'quests/supplemental.json').read_text(encoding='utf-8'))['quests'])
b._quest_eval=evaluate_document(b.quest_doc,{})
b.markers=[{'id':'boss:1','cat':'boss','names':{'zh':'Test Boss'},'master':'M00','px':5300,'py':5300,'h':44,'_uiIcon':'categories/anon.png'}]
b.marker_by_id={x['id']:x for x in b.markers}
b.catalog={'items':[{'key':'weapon:1','type':'weapon','id':1,'category':'armaments','collectible':True,'names':{'zh':'Test Sword'},'descriptions':{'zh':'Item description\nLine 2'},'icon':'weapon.png'}]}
b.characters=[{'slot':0,'name':'Test Hero','ok':True,'position':{'x':3,'y':44,'z':5,'mapId':'m60_43_36_00'},'mapPixel':{'px':5300,'py':5300,'h':44,'master':'M00'}}]; b.active_slot=0
messages=[]
def msg(kind,ctx,txt):
 messages.append(txt); print(txt)
qInstallMessageHandler(msg)
e=QQmlApplicationEngine(); e.rootContext().setContextProperty('backend',b); e.load(QUrl.fromLocalFile(str(Path('eldenringtool/qml/Main.qml').resolve())))
if not e.rootObjects(): sys.exit(1)
w=e.rootObjects()[0]
QTest.qWait(500)
# Screenshots are optional; this test checks actual pointer events.
print('MAIN LOADED')
# QObject objectNames enable meaningful synthetic interaction, no game resources required.
mp=w.findChild(QObject,'mapRoot'); flick=w.findChild(QObject,'mapViewport')
assert mp is not None and flick is not None
assert mp.property('hideCompleted') is True
b.setDisplaySetting('mapHideCompleted', False)
QTest.qWait(100)
assert mp.property('hideCompleted') is False
b.characters.append({'slot': 1, 'name': 'Other Hero'})
b.setActiveSlot(1); QTest.qWait(100)
assert mp.property('hideCompleted') is True
b.characters[0]['ok'] = False
b.setActiveSlot(0); QTest.qWait(100)
assert mp.property('hideCompleted') is False
locate = w.findChild(QObject, 'locatePlayerButton')
player = w.findChild(QObject, 'playerMarker')
assert locate is not None and player is not None and locate.property('enabled')
mp.setProperty('master', 'M01')
QTest.qWait(100)
assert not player.property('visible')
at = locate.mapToScene(QPointF(19, 19)).toPoint()
QTest.mouseClick(w, Qt.LeftButton, Qt.NoModifier, at)
QTest.qWait(150)
assert mp.property('master') == 'M00' and player.property('visible')
assert abs(flick.property('contentX') + flick.width()/2 - 5300*mp.property('mapZoom')) < 1
b.characters[0]['mapPixel'] = {'px': 5400, 'py': 5100, 'master': 'M10', 'h': 50}
b.characterChanged.emit()
QTest.qWait(100)
QTest.mouseClick(w, Qt.LeftButton, Qt.NoModifier, at)
QTest.qWait(150)
assert mp.property('master') == 'M10' and player.property('visible')
b.characters[0].pop('mapPixel')
b.characterChanged.emit()
QTest.qWait(100)
assert not locate.property('enabled') and not player.property('visible')
if mp:
 old=mp.property('mapZoom'); point=mp.mapToScene(QPointF(mp.width()/2,mp.height()/2))
 ev=QWheelEvent(point,point,QPoint(),QPoint(0,120),Qt.NoButton,Qt.NoModifier,Qt.NoScrollPhase,False)
 app.sendEvent(w,ev); QTest.qWait(150)
 print('ZOOM',old,mp.property('mapZoom')); assert mp.property('mapZoom')>old
 start=flick.property('contentX'); at=point.toPoint()
 QTest.mousePress(w,Qt.LeftButton,Qt.NoModifier,at)
 QTest.mouseMove(w,at+QPoint(30,0),40); QTest.mouseMove(w,at+QPoint(100,40),40)
 QTest.mouseRelease(w,Qt.LeftButton,Qt.NoModifier,at+QPoint(100,40))
 released=flick.property('contentX'); QTest.qWait(150)
 assert abs(flick.property('contentX')-released)>1, 'Pan should continue after release'
 print('PAN',start,flick.property('contentX')); assert flick.property('contentX')!=start
nav=w.findChild(QObject,'mainNav')
assert nav is not None
if nav:
 assert w.findChild(QObject,'catalogRoot').property('catalogModel').toVariant() == []
 for i,name in [(1,'quests'),(2,'catalog')]:
  nav.setProperty('currentIndex',i); QTest.qWait(200); assert w.isVisible()
# A save refresh during thumb dragging must not reset the grid or fight the pointer.
catalog = w.findChild(QObject, 'catalogRoot')
grid = w.findChild(QObject, 'catalogGrid')
bar = w.findChild(QObject, 'catalogScrollBar')
original_catalog = b.catalog
b.catalog = {'items': [{**original_catalog['items'][0], 'key': f'weapon:{i}', 'id': i,
                       'names': {'zh': f'Sword {i}'}, 'contentPack': '黄金树幽影'} for i in range(400)]}
b.dataChanged.emit(); QTest.qWait(250)
from PySide6.QtTest import QSignalSpy
rows_model = w.findChild(QObject, 'catalogRows')
reset_spy = QSignalSpy(rows_model.modelReset)
change_spy = QSignalSpy(rows_model.dataChanged)
thumb = bar.mapToScene(QPointF(bar.width()/2, bar.height()*bar.property('visualSize')/2)).toPoint()
QTest.mousePress(w, Qt.LeftButton, Qt.NoModifier, thumb)
assert bar.property('pressed')
last_y = grid.property('contentY')
for step in range(1, 6):
 QTest.mouseMove(w, thumb + QPoint(0, step*35), 25)
 b.catalog['items'][0]['descriptions'] = {'zh': f'Updated during drag {step}'}
 b.dataChanged.emit(); QTest.qWait(160)
 current_y = grid.property('contentY')
 assert current_y > last_y, (last_y, current_y)
 last_y = current_y
QTest.mouseRelease(w, Qt.LeftButton, Qt.NoModifier, thumb + QPoint(0, 175))
QTest.qWait(250)
assert abs(grid.property('contentY') - last_y) < 1, 'Refresh must preserve scroll offset'
b.characterChanged.emit(); b.dataChanged.emit(); QTest.qWait(250)
assert abs(grid.property('contentY') - last_y) < 1, 'Unchanged rows must keep scroll offset'
assert reset_spy.count() == 0, 'Save updates must not reset the entire model'
assert change_spy.count() == 1, 'Only the changed item should be updated after the drag'
catalog.setProperty('selectedCategory', 'talismans')
from PySide6.QtCore import QMetaObject
QMetaObject.invokeMethod(catalog, 'refresh'); QTest.qWait(250)
assert grid.property('count') == 0
assert abs(grid.property('contentY') - grid.property('originY')) < 1
catalog.setProperty('selectedCategory', 'all')
b.catalog = original_catalog
b.dataChanged.emit(); QTest.qWait(250)
print('CATALOG DRAG/REFRESH PASS')
# DLC changes update filters in place and are isolated from other save files.
b.save_path = str(Path(state_dir.name)/'ER0000.co2')
b.savePathChanged.emit()
b.catalog = {'items': [
 {**original_catalog['items'][0], 'key': 'weapon:1', 'id': 1},
 {**original_catalog['items'][0], 'key': 'weapon:2', 'id': 2, 'contentPack': '黄金树幽影'},
 {**original_catalog['items'][0], 'key': 'weapon:3', 'id': 3, 'contentPack': '褪色者礼包'}]}
b.catalogChanged.emit(); QTest.qWait(200)
assert grid.property('count') == 3
b.setContentPack('dlc', 'hide'); b.setContentPack('tarnished', 'hide'); QTest.qWait(200)
assert grid.property('count') == 1
b.setContentPack('dlc', 'show'); QTest.qWait(200)
assert grid.property('count') == 2
b.setContentPack('tarnished', 'show')
b.catalog = original_catalog; b.catalogChanged.emit(); QTest.qWait(200)
nav.setProperty('currentIndex', 3); QTest.qWait(200)
path_input = w.findChild(QObject, 'savePathInput')
assert path_input is not None and path_input.property('visible')
assert w.grabWindow().save(str(DATA.parent/'cache'/'save-content-settings.png'))
nav.setProperty('currentIndex', 2); QTest.qWait(200)
print('DLC FILTERS / SETTINGS PASS')
if '--screenshots' in sys.argv:
 from eldenringtool.core.catalog import build_index
 b.catalog=json.loads((DATA/'catalog.json').read_text(encoding='utf-8'))
 b.catalog_index=build_index(b.catalog)
 b.dataChanged.emit()
 quest=w.findChild(QObject,'questRoot')
 catalog=w.findChild(QObject,'catalogRoot')
 nav.setProperty('currentIndex',1); QTest.qWait(250)
 quest.setProperty('packFilter','tarnished')
 from PySide6.QtCore import QMetaObject
 QMetaObject.invokeMethod(quest,'refresh'); QTest.qWait(250)
 quests=quest.property('questModel')
 if hasattr(quests,'toVariant'): quests=quests.toVariant()
 quest.setProperty('selectedIndex',next(i for i,q in enumerate(quests) if q['id']=='tarnished_broken_goldmask'))
 QTest.qWait(150)
 def visual_find(item,name):
  if item.objectName()==name: return item
  for child in item.childItems():
   found=visual_find(child,name)
   if found is not None: return found
 switch=visual_find(w.contentItem(),'questStepSwitch_regression')
 assert switch is not None and switch.property('visible')
 for expected in (True, False):
  QTest.mouseClick(w,Qt.LeftButton,Qt.NoModifier,switch.mapToScene(QPointF(18,16)).toPoint())
  QTest.qWait(250)
  switch=visual_find(w.contentItem(),'questStepSwitch_regression')
  assert switch.property('checked') == expected
  assert b.store.quest_done(b.save_path,b.characters[0],'tarnished_broken_goldmask','regression') == expected
 # Completing Thops without ticking the spare-key guide must check the switch
 # retrospectively, without manufacturing a persistent manual confirmation.
 b._quest_eval = evaluate_document(b.quest_doc, {'_flags': {400362: True}})
 quest.setProperty('packFilter', 'base')
 QMetaObject.invokeMethod(quest, 'refresh'); QTest.qWait(250)
 quests = quest.property('questModel')
 if hasattr(quests, 'toVariant'): quests = quests.toVariant()
 quest.setProperty('selectedIndex', next(i for i, q in enumerate(quests) if q['id'] == 'thops'))
 QTest.qWait(150)
 switch = visual_find(w.contentItem(), 'questStepSwitch_second_key')
 assert switch is not None and switch.property('checked') and not switch.property('enabled')
 assert all(step['complete'] for step in next(q for q in quests if q['id'] == 'thops')['steps'])
 assert not b.store.quest_done(b.save_path, b.characters[0], 'thops', 'second_key')
 print('THOPS RETROSPECTIVE GUIDE PASS')
 for width,height in [(1540,920),(1120,700)]:
  w.setWidth(width); w.setHeight(height)
  nav.setProperty('currentIndex',1); QTest.qWait(250)
  assert w.grabWindow().save(str(DATA.parent/'cache'/f'quest-update-{width}.png'))
  nav.setProperty('currentIndex',2)
  catalog.setProperty('packFilter','褪色者礼包')
  QMetaObject.invokeMethod(catalog,'refresh'); QTest.qWait(250)
  rows=catalog.property('catalogModel')
  if hasattr(rows,'toVariant'): rows=rows.toVariant()
  assert len(rows)==29, len(rows)
  assert w.grabWindow().save(str(DATA.parent/'cache'/f'catalog-update-{width}.png'))
  catalog.setProperty('selectedItem',next(r for r in rows if r['key']=='weapon:67530000'))
  popup=w.findChild(QObject,'catalogDetail')
  QMetaObject.invokeMethod(popup,'open'); QTest.qWait(250)
  assert w.grabWindow().save(str(DATA.parent/'cache'/f'catalog-detail-update-{width}.png'))
  QMetaObject.invokeMethod(popup,'close')
 nav.setProperty('currentIndex', 0)
 b.tile_manifest=json.loads((DATA.parent/'assets/tiles/manifest.json').read_text(encoding='utf-8'))
 b._auto_found={'boss:1'}
 mp.setProperty('master','M00')
 fit=w.findChild(QObject,'fitMapButton')
 for width,height in [(1540,920),(1120,700)]:
  w.setWidth(width); w.setHeight(height); QTest.qWait(100)
  QTest.mouseClick(w,Qt.LeftButton,Qt.NoModifier,fit.mapToScene(QPointF(19,19)).toPoint())
  QTest.qWait(500)
  assert w.grabWindow().save(str(DATA.parent/'cache'/f'map-refinement-{width}.png'))
b.shutdown(); e.deleteLater(); QTest.qWait(20)
state_dir.cleanup()
assert not any('TypeError' in m or 'ReferenceError' in m or 'Binding loop' in m for m in messages),messages
print('UI PASS')
