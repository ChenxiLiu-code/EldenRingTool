import hashlib, json, os, struct
from pathlib import Path
import pytest

from eldenringtool.core.resource_cache import normalize_game_dir, build_manifest, atomic_json, manifest_path, validate_cache
from eldenringtool.core.projector import Projector
from eldenringtool.core.catalog import build_index, lookup, resolve
from eldenringtool.core.quest_engine import eval_condition, evaluate_quest
from eldenringtool.core.save_reader import read_bnd4, entry_payload, SaveError
from eldenringtool.core.state_store import StateStore

class Flags:
    def __init__(self,*on): self.on=set(on)
    def get(self,n): return int(n) in self.on

def test_inventory_direct_ids_and_instanced_equipment():
    from eldenringtool.core.save_reader import read_inventory
    held_size = 4 + 0xa80*12 + 4 + 0x180*12 + 8
    pay = bytearray(held_size + 4 + 0x780*12 + 4 + 0x80*12 + 8)
    def entry(offset, handle, quantity):
        struct.pack_into('<III', pay, offset, handle, quantity, 0)
    entry(4, 0xb0000000 | 3200, 1)  # Prattling Pate
    entry(16, 0xa0000000 | 1000, 1)
    entry(28, 0x80000001, 2)
    entry(40, 0x90000001, 1)
    entry(52, 0xc0000001, 1)
    entry(64, 0x80000002, 1)  # Unresolved equipment is not a direct ID.
    entry(76, 0xb0000000 | 9999, 0)
    key_offset = 4 + 0xa80*12 + 4
    entry(key_offset, 0xb0000000 | 8590, 1)
    entry(key_offset + 12, 0xb0000000 | 9300, 1)
    entry(held_size + 4, 0xa0000000 | 1000, 2)
    w = {'inventoryHeld': 0, 'inventoryStorage': held_size, 'gaItems': {
        0x80000001: {'itemId': 1000000}, 0x90000001: {'itemId': 10000},
        0xc0000001: {'itemId': 100}}}
    raw = read_inventory(pay, w)
    rows = {(r['type'], r['id']): r for r in raw['items']}
    assert raw['unknownHandles'] == 1
    assert len(rows) == 7
    assert rows['accessory', 1000]['quantity'] == 3
    assert rows['accessory', 1000]['held'] == 1
    assert rows['accessory', 1000]['storage'] == 2
    assert rows['goods', 8590]['held'] == 1
    assert rows['goods', 9300]['held'] == 1
    assert rows['weapon', 1000000]['quantity'] == 2


def test_equipment_icon_definitions():
    from tools.erlib import paramdef
    root = Path(__file__).resolve().parents[1]
    for name, field in [('Goods', 'iconId'), ('Weapon', 'iconId'),
                        ('Protector', 'iconIdM'), ('Accessory', 'iconId'), ('Gem', 'iconId')]:
        definition = paramdef.load(root / 'data' / 'paramdefs' / f'EquipParam{name}.xml')
        data = bytearray(definition.row_size)
        struct.pack_into('<H', data, definition.by_name[field].offset, 1234)
        assert definition.get(data, field) == 1234

def test_game_dir_normalization_and_version_gate(tmp_path):
    root=tmp_path/'app'; gd=tmp_path/'ELDEN RING'/'Game';gd.mkdir(parents=True);root.mkdir()
    (gd/'eldenring.exe').write_bytes(b'exe');(gd/'regulation.bin').write_bytes(b'reg')
    # A real scan manifest contains a non-empty tile index and corresponding tiles.
    tile_manifest={"format":"webp","masters":{"M00":{"tiles":{"0":[[0,0]]}}}}
    p=root/'assets/tiles/manifest.json';p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(tile_manifest))
    tile=root/'assets/tiles/M00/0/0/0.webp';tile.parent.mkdir(parents=True,exist_ok=True);tile.write_bytes(b'tile')
    for rel in ('data/markers.json','data/items.json','data/unique_drops.json','data/mausoleums.json','data/catalog.json','data/legacy-conv.json'):
        p=root/rel;p.parent.mkdir(parents=True,exist_ok=True);p.write_text('{}')
    assert normalize_game_dir(gd/'eldenring.exe')==gd.resolve()
    m=build_manifest(root,gd);atomic_json(manifest_path(root),m)
    assert validate_cache(root).valid
    # mtime-only mutation must not force a reparse when content hash is unchanged.
    p=gd/'regulation.bin';os.utime(p,ns=(p.stat().st_atime_ns,p.stat().st_mtime_ns+10_000))
    s=validate_cache(root);assert s.valid and s.metadata_refreshed
    p.write_bytes(b'changed')
    s=validate_cache(root);assert not s.valid and '版本变化' in s.reason

def test_projector_overworld():
    p=Projector({'rows':[],'undergroundBlocks':[]})
    r=p.project({'mapBytes':[0,10,20,60],'x':1.25,'y':99.2,'z':-2.0})
    assert r=={'px':round(20*256+128+1.25-7168,1),'py':round(16640-(10*256+128-2.0),1),'h':99,'master':'M00'}

def test_catalog_weapon_upgrade_alias():
    row={'type':'weapon','id':1000000,'key':'weapon:1000000','aliases':[1000000,1010000]}
    idx=build_index({'items':[row]})
    assert lookup(idx,'weapon',1010012) is row
    out=resolve(idx,{'items':[{'type':'weapon','id':1010012,'quantity':1,'held':1,'storage':0}]})
    assert out['distinct']==1 and out['quantity']==1

def test_quest_branch_and_manual():
    q={'id':'q','steps':[
      {'id':'a','completeWhen':{'flag':1}},
      {'id':'choiceA','guideOnly':True,'manual':True,'exclusiveGroup':'g','exclusiveOption':'A'},
      {'id':'choiceB','guideOnly':True,'manual':True,'exclusiveGroup':'g','exclusiveOption':'B'},
      {'id':'end','completeWhen':{'flag':2},'impliedBySteps':['a']},
    ]}
    s=evaluate_quest(q,Flags(1),set(),lambda qid,sid:sid=='choiceA')
    states={x['id']:x for x in s['steps']}
    assert states['a']['complete']
    assert states['choiceB']['missed']
    assert states['end']['inferred']


def test_cache_rejects_missing_tile(tmp_path):
    root=tmp_path/'app';gd=tmp_path/'Game';root.mkdir();gd.mkdir()
    (gd/'eldenring.exe').write_bytes(b'exe');(gd/'regulation.bin').write_bytes(b'reg')
    manifest={"format":"webp","masters":{"M00":{"tiles":{"0":[[0,0]]}}}}
    p=root/'assets/tiles/manifest.json';p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(manifest))
    tile=root/'assets/tiles/M00/0/0/0.webp';tile.parent.mkdir(parents=True,exist_ok=True);tile.write_bytes(b'x')
    for rel in ('data/markers.json','data/items.json','data/unique_drops.json','data/mausoleums.json','data/catalog.json','data/legacy-conv.json'):
        p=root/rel;p.parent.mkdir(parents=True,exist_ok=True);p.write_text('{}')
    atomic_json(manifest_path(root),build_manifest(root,gd))
    tile.unlink()
    status=validate_cache(root)
    assert not status.valid and '瓦片缺失' in status.reason


def test_cache_rejects_zero_byte_tile(tmp_path):
    root=tmp_path/'app';gd=tmp_path/'Game';root.mkdir();gd.mkdir()
    (gd/'eldenring.exe').write_bytes(b'exe');(gd/'regulation.bin').write_bytes(b'reg')
    manifest={"format":"webp","masters":{"M00":{"tiles":{"0":[[0,0]]}}}}
    p=root/'assets/tiles/manifest.json';p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(manifest))
    tile=root/'assets/tiles/M00/0/0/0.webp';tile.parent.mkdir(parents=True,exist_ok=True);tile.write_bytes(b'')
    for rel in ('data/markers.json','data/items.json','data/unique_drops.json','data/mausoleums.json','data/catalog.json','data/legacy-conv.json'):
        p=root/rel;p.parent.mkdir(parents=True,exist_ok=True);p.write_text('{}')
    with pytest.raises(RuntimeError, match='地图瓦片为空'):
        build_manifest(root,gd)


def test_cache_rejects_missing_required_marker_corpus(tmp_path):
    root=tmp_path/'app';gd=tmp_path/'Game';root.mkdir();gd.mkdir()
    (gd/'eldenring.exe').write_bytes(b'exe');(gd/'regulation.bin').write_bytes(b'reg')
    manifest={"format":"webp","masters":{"M00":{"tiles":{"0":[[0,0]]}}}}
    p=root/'assets/tiles/manifest.json';p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(manifest))
    tile=root/'assets/tiles/M00/0/0/0.webp';tile.parent.mkdir(parents=True,exist_ok=True);tile.write_bytes(b'x')
    for rel in ('data/markers.json','data/items.json','data/unique_drops.json','data/mausoleums.json','data/catalog.json','data/legacy-conv.json'):
        p=root/rel;p.parent.mkdir(parents=True,exist_ok=True);p.write_text('{}')
    atomic_json(manifest_path(root),build_manifest(root,gd))
    (root/'data/unique_drops.json').unlink()
    status=validate_cache(root)
    assert not status.valid and 'unique_drops.json' in status.reason


def test_mod_cache_requires_pieces(tmp_path):
    root=tmp_path/'app';gd=tmp_path/'Game';md=tmp_path/'mod';root.mkdir();gd.mkdir();md.mkdir()
    (gd/'eldenring.exe').write_bytes(b'exe');(gd/'regulation.bin').write_bytes(b'reg');(md/'regulation.bin').write_bytes(b'modreg')
    manifest={"format":"webp","masters":{"M00":{"tiles":{"0":[[0,0]]}}}}
    p=root/'assets/tiles/manifest.json';p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(manifest))
    tile=root/'assets/tiles/M00/0/0/0.webp';tile.parent.mkdir(parents=True,exist_ok=True);tile.write_bytes(b'x')
    for rel in ('data/markers.json','data/items.json','data/unique_drops.json','data/mausoleums.json','data/catalog.json','data/legacy-conv.json','data/pieces.json'):
        p=root/rel;p.parent.mkdir(parents=True,exist_ok=True);p.write_text('{}')
    atomic_json(manifest_path(root),build_manifest(root,gd,md))
    assert validate_cache(root).valid
    (root/'data/pieces.json').unlink()
    status=validate_cache(root)
    assert not status.valid and 'pieces.json' in status.reason

def test_character_scoped_manual_markers_and_legacy_import(tmp_path):
    path=tmp_path/'user-state.json'
    path.write_text(json.dumps({"checked":{"marker:A":True,"queststep:0:Hero:q:s":True}}),encoding='utf-8')
    store=StateStore(path)
    a={"slot":0,"name":"Hero"}; b={"slot":1,"name":"Alt"}
    save=tmp_path/'7656119'/'ER0000.sl2';save.parent.mkdir();save.write_bytes(b'')
    # Legacy shared markers do not auto-apply to either character.
    assert not store.marker_checked(save,a,'marker:A')
    assert not store.marker_checked(save,b,'marker:A')
    assert store.import_legacy_markers(save,a,{'marker:A','marker:B'})==1
    assert store.marker_checked(save,a,'marker:A')
    assert not store.marker_checked(save,b,'marker:A')
    store.set_marker_checked(save,b,'marker:B',True)
    assert not store.marker_checked(save,a,'marker:B')
    assert store.marker_checked(save,b,'marker:B')

def _fake_bnd4():
    # One plaintext entry using the save BND4 directory format.
    payload=b'hello save payload long enough';body=hashlib.md5(payload).digest()+payload
    name='USER_DATA000'.encode('utf-16le')+b'\0\0'; nameoff=0x80;dataoff=0x100
    b=bytearray(dataoff+len(body));b[:4]=b'BND4';struct.pack_into('<I',b,0x0c,1)
    struct.pack_into('<Q',b,0x48,len(body));struct.pack_into('<I',b,0x50,dataoff);struct.pack_into('<I',b,0x54,nameoff)
    b[nameoff:nameoff+len(name)]=name;b[dataoff:dataoff+len(body)]=body
    return bytes(b)

def test_bnd4_plaintext_entry():
    b=_fake_bnd4();e=read_bnd4(b)[0];p,enc,ok=entry_payload(b,e)
    assert e['name']=='USER_DATA000' and p==b'hello save payload long enough' and ok and not enc

def test_bnd4_rejects_truncated_directory():
    b=bytearray(0x50);b[:4]=b'BND4';struct.pack_into('<I',b,0x0c,10)
    with pytest.raises(SaveError):read_bnd4(bytes(b))


def test_mod_cache_detects_loose_dcx_change(tmp_path):
    root=tmp_path/'app';gd=tmp_path/'Game';md=tmp_path/'mod';root.mkdir();gd.mkdir();md.mkdir()
    (gd/'eldenring.exe').write_bytes(b'exe');(gd/'regulation.bin').write_bytes(b'reg');(md/'regulation.bin').write_bytes(b'modreg')
    loose=md/'map'/'MapStudio'/'m10_00_00_00.msb.dcx';loose.parent.mkdir(parents=True);loose.write_bytes(b'a')
    tile_manifest={"format":"webp","masters":{"M00":{"tiles":{"0":[[0,0]]}}}}
    p=root/'assets/tiles/manifest.json';p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(tile_manifest))
    tile=root/'assets/tiles/M00/0/0/0.webp';tile.parent.mkdir(parents=True,exist_ok=True);tile.write_bytes(b'tile')
    for rel in ('data/markers.json','data/items.json','data/unique_drops.json','data/mausoleums.json','data/catalog.json','data/legacy-conv.json','data/pieces.json'):
        p=root/rel;p.parent.mkdir(parents=True,exist_ok=True);p.write_text('{}')
    atomic_json(manifest_path(root),build_manifest(root,gd,md))
    assert validate_cache(root).valid
    loose.write_bytes(b'changed')
    status=validate_cache(root)
    assert not status.valid and '模组松散资源变化' in status.reason


def test_dependency_probe_uses_soulstruct_havok_namespace(monkeypatch):
    from eldenringtool.core import scanner

    probed = []

    def fake_find_spec(name):
        probed.append(name)
        return object()

    monkeypatch.setattr(scanner.importlib.util, "find_spec", fake_find_spec)
    assert scanner.missing_dependencies() == []
    assert "Crypto.Cipher.AES" in probed
    assert not any(name.startswith("soulstruct") for name in probed)


def test_dotted_dependency_probe_handles_missing_parent(monkeypatch):
    from eldenringtool.core import scanner

    def fake_find_spec(name):
        if name == "Crypto.Cipher.AES":
            raise ModuleNotFoundError("parent missing")
        return object()

    monkeypatch.setattr(scanner.importlib.util, "find_spec", fake_find_spec)
    assert "pycryptodome" in scanner.missing_dependencies()


def test_marker_icon_resolves_category_directory(tmp_path):
    from eldenringtool.core.assets import marker_icon_name

    assets = tmp_path / "assets"
    root_icon = assets / "icons" / "123.png"
    category_icon = assets / "icons" / "categories" / "quest.png"
    root_icon.parent.mkdir(parents=True)
    category_icon.parent.mkdir(parents=True)
    root_icon.write_bytes(b"x")
    category_icon.write_bytes(b"x")

    assert marker_icon_name(assets, 123) == "123.png"
    assert marker_icon_name(assets, "quest.png") == "categories/quest.png"
    assert marker_icon_name(assets, "../secret.png") == ""
    assert marker_icon_name(assets, "missing.png") == ""


def test_quest_confirmations_are_account_scoped_for_new_writes(tmp_path):
    store = StateStore(tmp_path / "state.json")
    char = {"slot": 0, "name": "Hero"}
    save_a = tmp_path / "111" / "ER0000.sl2"
    save_b = tmp_path / "222" / "ER0000.sl2"
    save_a.parent.mkdir(); save_b.parent.mkdir()
    save_a.write_bytes(b""); save_b.write_bytes(b"")

    store.set_quest_done(save_a, char, "q", "step", True)
    assert store.quest_done(save_a, char, "q", "step")
    assert not store.quest_done(save_b, char, "q", "step")


def test_cache_detects_bdt_metadata_change(tmp_path):
    root=tmp_path/'app'; gd=tmp_path/'Game'; root.mkdir(); gd.mkdir()
    (gd/'eldenring.exe').write_bytes(b'exe'); (gd/'regulation.bin').write_bytes(b'reg')
    (gd/'Data0.bhd').write_bytes(b'header'); (gd/'Data0.bdt').write_bytes(b'payload')
    tile_manifest={"format":"webp","masters":{"M00":{"tiles":{"0":[[0,0]]}}}}
    p=root/'assets/tiles/manifest.json'; p.parent.mkdir(parents=True,exist_ok=True); p.write_text(json.dumps(tile_manifest))
    tile=root/'assets/tiles/M00/0/0/0.webp'; tile.parent.mkdir(parents=True,exist_ok=True); tile.write_bytes(b'tile')
    for rel in ('data/markers.json','data/items.json','data/unique_drops.json','data/mausoleums.json','data/catalog.json','data/legacy-conv.json'):
        p=root/rel; p.parent.mkdir(parents=True,exist_ok=True); p.write_text('{}')
    atomic_json(manifest_path(root), build_manifest(root, gd))
    assert validate_cache(root).valid
    bdt = gd/'Data0.bdt'
    bdt.write_bytes(b'payload changed')
    status = validate_cache(root)
    assert not status.valid and '归档数据变化' in status.reason


def test_stream_process_can_cancel_silent_child(tmp_path):
    import os, sys, time
    from eldenringtool.core import scanner

    start = time.monotonic()
    def cancelled():
        return time.monotonic() - start > 0.2

    with pytest.raises(InterruptedError, match="解析已取消"):
        scanner._stream_process(
            [sys.executable, "-c", "import time; time.sleep(30)"],
            tmp_path,
            os.environ.copy(),
            cancelled=cancelled,
        )
    assert time.monotonic() - start < 5
