import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import pytest
import copy
from PySide6.QtCore import QCoreApplication
from eldenringtool.backend import Backend
from eldenringtool.core.catalog import build_index
from eldenringtool.core.state_store import StateStore

@pytest.fixture
def backend(tmp_path, monkeypatch):
    from types import SimpleNamespace
    monkeypatch.setattr('eldenringtool.backend.validate_cache', lambda root: SimpleNamespace(valid=False, reason='', game_dir=''))
    monkeypatch.setattr('eldenringtool.backend.recover_interrupted_scan', lambda root: None)
    app = QCoreApplication.instance() or QCoreApplication([])
    b=Backend(); b.timer.stop(); b.store=StateStore(tmp_path/'state.json')
    yield b
    b.shutdown()

def item(i,cat='armaments',name='Sword',**kw):
    return dict(key=f'weapon:{i}',type='weapon',id=i,category=cat,names={'zh':name},**kw)


def update_context(backend, character):
    backend.catalog = {'items': [item(1, collectible=True)]}
    backend.catalog_index = build_index(backend.catalog)
    backend.characters = [character]
    backend.active_slot = 0
    backend.save_path = 'account/save.sl2'
    backend.markers = [{'id': 'boss:1', 'flag': 1}]
    backend.quest_doc = {'quests': [{'id': 'q', 'completeWhen': {'flag': 1}, 'steps': []}]}
    backend._recompute_character()
    return dict(store=backend.store, path=backend.save_path, slot=0, characters=backend.characters,
                generation=backend._save_generation, found=backend._auto_found, collection=backend._collection,
                quests=backend._quest_eval, markers=backend.markers, catalog=backend.catalog,
                index=backend.catalog_index, quest_doc=backend.quest_doc, projector=backend.projector)


def snapshot_character():
    from eldenringtool.core.save_reader import EventFlags
    return {'slot': 0, 'name': 'Hero', 'ok': True, 'secondsPlayed': 10,
            '_flags': EventFlags(bytes(125), 0, {0: 0}), '_inventoryRaw': {'items': []}, '_gestureIds': []}


@pytest.mark.parametrize('change,expected', [
    ('none', (False, False, False, False)),
    ('time', (True, False, False, False)),
    ('position', (True, False, False, False)),
    ('unrelated_flag', (False, False, False, False)),
    ('inventory', (True, False, True, False)),
    ('flag', (True, True, False, True)),
])
def test_save_update_emits_only_changed_domains(backend, change, expected):
    from eldenringtool.core.save_updates import prepare_update
    context = update_context(backend, snapshot_character())
    character = copy.deepcopy(context['characters'][0])
    if change == 'time': character['secondsPlayed'] += 1
    if change == 'position': character['position'] = {'x': 0, 'y': 0, 'z': 0, 'mapId': 'm60_43_36_00'}
    if change == 'unrelated_flag': character['_flags'].pay = b'\x01' + bytes(124)
    if change == 'inventory': character['_inventoryRaw']['items'] = [{'type': 'weapon', 'id': 1, 'quantity': 1}]
    if change == 'flag': character['_flags'].pay = b'\x40' + bytes(124)
    result = prepare_update({'characters': [character]}, backend.save_path, context)
    assert tuple(result[k] for k in ('character_changed', 'map_changed', 'catalog_changed', 'quests_changed')) == expected
    seen = []
    for key in ('character', 'map', 'catalog', 'quests', 'data'):
        getattr(backend, key + 'Changed').connect(lambda key=key: seen.append(key))
    backend._setup = False
    backend._on_save_done(result, backend.save_path, 123)
    assert seen == [key for key, changed in zip(('character', 'map', 'catalog', 'quests'), expected) if changed]
    assert backend._save_mtime_ns == 123


def test_stale_save_result_does_not_overwrite_character(backend):
    from eldenringtool.core.save_updates import prepare_update
    context = update_context(backend, snapshot_character())
    result = prepare_update({'characters': []}, backend.save_path, context)
    backend._setup = False
    backend._save_generation += 1
    backend._on_save_done(result, 'old-save.sl2', 123)
    assert backend.characters[0]['name'] == 'Hero'
    assert backend.save_path == 'account/save.sl2'
    assert backend._save_pending


def test_save_comparison_and_derivation_run_off_ui_thread(backend, tmp_path, monkeypatch):
    from PySide6.QtCore import QThread, QEventLoop, QTimer
    import eldenringtool.backend as module
    character = snapshot_character()
    update_context(backend, character)
    path = tmp_path / 'ER0000.sl2'
    path.write_bytes(b'BND4')
    backend.save_path = str(path)
    backend._setup = False
    monkeypatch.setattr(backend, '_find_save', lambda: path)
    seen = []
    def read(reader):
        seen.append(('read', QThread.currentThread() != backend.thread()))
        return {'characters': [copy.deepcopy(character)]}
    original = module.prepare_update
    def prepare(*args):
        seen.append(('diff', QThread.currentThread() != backend.thread()))
        return original(*args)
    monkeypatch.setattr(module.SaveReader, 'read', read)
    monkeypatch.setattr(module, 'prepare_update', prepare)
    loop = QEventLoop()
    backend.refresh_save(True)
    backend._save_thread.finished.connect(loop.quit)
    QTimer.singleShot(5000, loop.quit)
    loop.exec()
    assert seen == [('read', True), ('diff', True)]
    assert backend._save_mtime_ns == path.stat().st_mtime_ns


def test_save_path_manual_validation_and_no_silent_fallback(backend, tmp_path, monkeypatch):
    monkeypatch.setattr(backend, 'refresh_save', lambda force=False: None)
    path = tmp_path / 'custom.co2'
    path.write_bytes(b'BND4')
    backend.setSavePath(str(path))
    assert backend.configuredSavePath == str(path.resolve())
    assert StateStore(backend.store.path).data['settings']['savePath'] == str(path.resolve())
    backend.setSavePath(str(tmp_path / 'missing.sl2'))
    assert backend.configuredSavePath == str(path.resolve())
    path.unlink()
    assert backend._find_save() == path.resolve()
    backend.setSavePath('')
    assert backend.configuredSavePath == ''


@pytest.mark.parametrize('dlc,tarnished', [('hide', 'hide'), ('hide', 'show'), ('show', 'hide'), ('unknown', 'unknown')])
def test_content_pack_filters_independent_and_persisted(backend, dlc, tarnished):
    backend.save_path = 'a/save.sl2'
    backend.catalog = {'items': [item(1), item(2, contentPack='黄金树幽影'), item(3, contentPack='褪色者礼包')]}
    backend.quest_doc = {'quests': [{'id': p, 'pack': p} for p in ('base', 'dlc', 'tarnished')]}
    backend.markers = [{'id': 'base', 'master': 'M00', 'px': 0, 'py': 0},
                       {'id': 'shadow', 'master': 'M10', 'px': 0, 'py': 0},
                       {'id': 'pack', 'master': 'M00', 'px': 1, 'py': 1}]
    backend._marker_packs = {'pack': {'褪色者礼包'}}
    backend.setContentPack('dlc', dlc)
    backend.setContentPack('tarnished', tarnished)
    assert [r['id'] for r in backend.catalogItems()] == [1] + ([2] if dlc != 'hide' else []) + ([3] if tarnished != 'hide' else [])
    assert {r['id'] for r in backend.questCards()} == {'base'} | ({'dlc'} if dlc != 'hide' else set()) | ({'tarnished'} if tarnished != 'hide' else set())
    assert backend.masterVisible('M10') == (dlc != 'hide')
    assert backend._marker_visible(backend.markers[2]) == (tarnished != 'hide')
    assert StateStore(backend.store.path).data['settings']['contentPacks']['a/save.sl2'] == {'dlc': dlc, 'tarnished': tarnished}
    backend.save_path = 'b/save.co2'
    assert backend.contentPacks == {'dlc': 'unknown', 'tarnished': 'unknown'}

def test_catalog_excludes_error_and_bulk(backend):
    backend.catalog={'items':[item(1,collectible=True),item(2,name='[ERROR] unknown',collectible=True),item(3,'consumables',collectible=False),item(4,'golden_runes',collectible=False)]}
    assert [x['id'] for x in backend.catalogItems()]==[1]


def test_catalog_owned_first_with_filters(backend):
    backend.catalog = {'items': [item(1, name='Missing sword'), item(2, name='Owned sword'), item(3, name='Other sword')]}
    backend._collection = {'owned': {'weapon:2': {'quantity': 1}}}
    assert [r['id'] for r in backend.catalogItems('armaments', 'sword')] == [2, 1, 3]
    assert [r['id'] for r in backend.catalogItems(missing_only=True)] == [1, 3]


def test_legacy_catalog_recovers_knife_and_dlc(backend):
    def goods(i, name, category='misc'):
        return dict(key=f'goods:{i}', type='goods', id=i, names={'en': name, 'zh': name}, category=category, collectible=False)
    doc = {'items': [goods(8590, 'Whetstone Knife', 'progression'),
                     goods(2007420, 'Cherishing Fingers'), goods(2007800, 'Fire Serpent'),
                     goods(2215010, 'Ancient Dragon Florissax +10'), goods(2215000, 'Ancient Dragon Florissax')]}
    backend.catalog_index = build_index(doc)
    backend.catalog = doc
    from eldenringtool.core.catalog import resolve
    backend._collection = resolve(backend.catalog_index, {'items': [{'type': 'goods', 'id': 2215010, 'quantity': 1}]})
    rows = backend.catalogItems()
    assert len(rows) == 4
    assert rows[0]['id'] == 2215000 and rows[0]['owned']
    assert backend.catalogItems('whetblades')[0]['id'] == 8590
    assert backend.catalogItems('sorceries')[0]['id'] == 2007420
    assert backend.catalogItems('incantations')[0]['id'] == 2007800
    assert {r['id'] for r in backend.catalogCategories()} == {'all', 'whetblades', 'sorceries', 'incantations', 'spirits'}
    assert len(build_index(doc)['doc']['items']) == 4


def test_extractor_classifies_missing_collectibles():
    from tools.erlib.mfg_categories import categorise
    assert categorise(8590, 'Whetstone Knife', 1) == 'whetblades'
    assert categorise(2007420, 'Cherishing Fingers', 1) == 'sorceries'
    assert categorise(2007800, 'Fire Serpent', 1) == 'incantations'
    assert categorise(2215010, 'Ancient Dragon Florissax +10', 1) == 'spirits'

def test_catalog_categories_icons_descriptions_and_sources(backend):
    backend.marker_by_id={'p':{'names':{'zh':'Chest'}}}
    backend.catalog={'items':[item(1,collectible=True,icon='weapon.png',descriptions={'zh':'Long description'},sources=[{'kind':'pickup','marker':'p'}],contentPack='黄金树幽影'),item(2,'world_maps',collectible=True)]}
    row=backend.catalogItems('armaments')[0]
    assert row['description']=='Long description' and row['pack']=='黄金树幽影'
    assert row['icon']=='categories/weapon.png' and row['sources'][0]['marker']=='p'
    assert [x['id'] for x in backend.catalogItems('other')]==[2]


def test_catalog_details_and_named_enemy_source(backend):
    backend.catalog = {'items': [item(
        1, collectible=True,
        details={'weight': 4.5, 'attack': [100, 0, 0, 0, 0]},
        sources=[{'kind': 'unique_drop', 'enemyName': 'Godrick the Grafted'}],
    )]}
    row = backend.catalogItems()[0]
    assert row['details']['weight'] == 4.5
    assert row['sources'][0]['text'].endswith('Godrick the Grafted')

def test_map_fragment_persistent_flag_without_inventory(backend):
    row={'key':'goods:1','type':'goods','id':1,'category':'world_maps','collectible':True,'names':{'zh':'Map'},'acquisitionFlags':[123]}
    backend.catalog={'items':[row]};backend.catalog_index=build_index(backend.catalog)
    backend.characters=[{'slot':0,'ok':True,'_flags':{123:True},'_inventoryRaw':{'items':[]}}];backend.active_slot=0
    backend._recompute_character()
    assert backend.catalogItems()[0]['owned'] is True
    assert backend.catalogItems(missing_only=True)==[]

def test_boss_survives_overview_clustering(backend):
    backend.markers=[{'id':f'm:{i}','cat':'item','px':100+i%5,'py':100+i%4,'master':'M00'} for i in range(200)]
    backend.markers.append({'id':'boss:1','cat':'boss','px':100,'py':100,'master':'M00','h':-42,'names':{'zh':'Boss'}})
    rows=backend.visibleMarkers('M00',0.05,0,0,1000,1000)
    bosses=[r for r in rows if r['cat']=='boss']
    assert len(bosses)==1 and not bosses[0]['cluster'] and bosses[0]['h']==-42
    assert any(r['cluster'] for r in rows)

def test_multi_category_and_none(backend):
    backend.markers=[{'id':str(i),'cat':cat,'px':10,'py':10,'master':'M00'} for i,cat in enumerate(('boss','grace','npc'))]
    assert {x['cat'] for x in backend.visibleMarkers('M00',1,0,0,100,100,'','boss,npc')}=={'boss','npc'}
    assert backend.visibleMarkers('M00',1,0,0,100,100,'','__none__')==[]

def test_quest_guide_and_auto_contract(backend):
    backend.quest_doc={'quests':[{'id':'q','pack':'base','name':'Quest','steps':[{'id':'g','guideOnly':True,'title':'Guide'},{'id':'a','title':'Auto','completeWhen':{'flag':1}}]}]}
    rows=backend.questCards('all','','base')[0]['steps']
    assert rows[0]['guideOnly'] and rows[0]['manualEligible']
    assert not rows[1]['guideOnly'] and not rows[1]['manualEligible']

def test_no_phantom_tiles_with_empty_manifest(backend):
    assert backend.visibleTiles('M00',0.1,0,0,1000,1000)==[]


def test_existing_catalog_recovers_packs_and_steed_appearances(backend):
    backend.catalog = {'items': [
        item(67530000, name='Idus Sword'),
        item(4500000, name='Meteoric Sword', contentPack='扩展内容 DLC01（归属待确认）'),
        item(1000, name='DLC dummy'),
        {'key': 'goods:2009600', 'type': 'goods', 'id': 2009600, 'category': 'misc',
         'collectible': False, 'names': {'en': 'Spectral Steed Regalia: Tree Sentinel'}},
    ]}
    backend.catalog_index = build_index(backend.catalog)
    assert len(backend.catalogItems()) == 3
    assert {r['pack'] for r in backend.catalogItems()} == {'褪色者礼包', '黄金树幽影'}
    assert len(backend.catalogItems(query='褪色者礼包')) == 2
    assert backend.catalogItems('steed_appearances')[0]['id'] == 2009600
    assert any(c['id'] == 'steed_appearances' for c in backend.catalogCategories())
    from tools.erlib.mfg_categories import categorise
    assert categorise(2009610, 'Spectral Steed Regalia: Carian Silver', 1) == 'steed_appearances'


def test_quest_switch_reversible_isolated_and_exclusive(backend):
    from eldenringtool.core.quest_engine import evaluate_document
    backend.characters = [{'slot': 0, 'name': 'A'}, {'slot': 1, 'name': 'B'}]
    backend.active_slot = 0
    backend.quest_doc = {'quests': [{'id': 'q', 'name': 'Quest', 'steps': [
        {'id': 'a', 'guideOnly': True, 'title': 'Choice A', 'action': 'Secret cellar',
         'exclusiveGroup': 'choice', 'exclusiveOption': 'a'},
        {'id': 'b', 'guideOnly': True, 'title': 'Choice B', 'reward': 'Rare shield',
         'exclusiveGroup': 'choice', 'exclusiveOption': 'b'},
        {'id': 'auto', 'title': 'Automatic', 'completeWhen': {'flag': 99}},
    ]}]}
    backend.setQuestStepChecked('q', 'a', True)
    assert backend.questCards(query='cellar')[0]['steps'][0]['manual']
    backend.setQuestStepChecked('q', 'b', True)
    steps = backend.questCards(query='shield')[0]['steps']
    assert not steps[0]['manual'] and steps[1]['manual']
    backend.setQuestStepChecked('q', 'b', False)
    assert not backend.questCards()[0]['steps'][1]['manual']
    backend.setQuestStepChecked('q', 'auto', True)
    assert not backend.store.quest_done(backend.save_path, backend.characters[0], 'q', 'auto')
    backend.setQuestStepChecked('q', 'a', True)
    backend.active_slot = 1
    backend._quest_eval = evaluate_document(backend.quest_doc, {}, (), lambda q, s: backend.store.quest_done(backend.save_path, backend.characters[1], q, s))
    assert not backend.questCards()[0]['steps'][0]['manual']


def test_supplemental_quests_and_ashen_capital_risk():
    import json
    from eldenringtool.backend import DATA
    from eldenringtool.core.quest_engine import evaluate_document
    doc = json.loads((DATA / 'quests' / 'supplemental.json').read_text(encoding='utf-8'))
    assert len({q['id'] for q in doc['quests']}) == 4
    state = evaluate_document(doc, {}, {'boss:13000800'})['states']['tarnished_broken_goldmask']
    assert state['risks'][0]['triggered']
    done = evaluate_document(doc, {}, {'boss:13000800'}, lambda q, s: True)['states']['tarnished_broken_goldmask']
    assert done['status'] == 'completed' and not done['risks']


def test_display_preferences_persist_per_account_character(tmp_path):
    path = tmp_path / 'state.json'
    store = StateStore(path)
    hero = {'slot': 0, 'name': 'Hero'}
    other = {'slot': 1, 'name': 'Hero'}
    defaults = {'mapHideCompleted': True, 'catalogHideCompleted': False}
    assert store.display_settings('account-a/save.sl2', hero) == defaults
    store.set_display_setting('account-a/save.sl2', hero, 'mapHideCompleted', False)
    store.set_display_setting('account-a/save.sl2', hero, 'catalogHideCompleted', True)
    store = StateStore(path)
    assert store.display_settings('account-a/save.sl2', hero) == {'mapHideCompleted': False, 'catalogHideCompleted': True}
    assert store.display_settings('account-b/save.sl2', hero) == defaults
    assert store.display_settings('account-a/save.sl2', other) == defaults


def test_character_switch_restores_preferences(backend):
    backend.characters = [{'slot': 0, 'name': 'A'}, {'slot': 1, 'name': 'B'}]
    backend.save_path = 'account/save.sl2'
    backend.setActiveSlot(0)
    backend.setDisplaySetting('mapHideCompleted', False)
    backend.setDisplaySetting('catalogHideCompleted', True)
    backend.setActiveSlot(1)
    assert backend.displaySettings == {'mapHideCompleted': True, 'catalogHideCompleted': False}
    backend.setActiveSlot(0)
    assert backend.displaySettings == {'mapHideCompleted': False, 'catalogHideCompleted': True}


def test_completed_markers_do_not_mix_with_incomplete_clusters(backend):
    backend.markers = [{'id': str(i), 'px': 100, 'py': 100, 'cat': 'item'} for i in range(200)]
    backend._auto_found = {str(i) for i in range(100)}
    rows = backend.visibleMarkers('M00', 0.1, 0, 0, 1000, 1000)
    assert len(rows) == 2
    assert {r['found'] for r in rows} == {True, False}
    assert all(r['count'] == 100 for r in rows)
    hidden = backend.visibleMarkers('M00', 0.1, 0, 0, 1000, 1000, '', '', True)
    assert len(hidden) == 100 and not any(r['found'] for r in hidden)


def test_save_poll_interval_applies_and_survives_restart(backend, monkeypatch):
    assert backend.savePollInterval == 1.2
    backend.setSavePollInterval(5.0)
    assert backend.timer.interval() == 5000
    store = StateStore(backend.store.path)
    monkeypatch.setattr('eldenringtool.backend.StateStore', lambda path: store)
    restarted = Backend()
    try:
        assert restarted.savePollInterval == 5.0
        assert restarted.timer.interval() == 5000
    finally:
        restarted.shutdown()
    backend.setSavePollInterval(0)
    assert backend.timer.interval() == 200
    backend.setSavePollInterval(999)
    assert backend.timer.interval() == 60000
    backend.setSavePollInterval(float('nan'))
    assert backend.timer.interval() == 60000


@pytest.mark.parametrize('value', [None, 'bad', True, float('inf')])
def test_invalid_saved_poll_interval_uses_default(backend, value):
    backend.store.data['settings']['savePollInterval'] = value
    assert backend.savePollInterval == 1.2
