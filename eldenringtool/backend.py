from __future__ import annotations

import json
import copy
import math
import os
import traceback
from pathlib import Path

from PySide6.QtCore import QObject, Property, QThread, QTimer, QUrl, Signal, Slot

from .core.assets import marker_icon_name
from .core.catalog import build_index, collection_category, content_pack, is_collectible, resolve as resolve_catalog
from .core.projector import Projector
from .core.quest_engine import evaluate_document, local_text
from .core.resource_cache import (
    clear_scan_cache, normalize_game_dir, recover_interrupted_scan, validate_cache,
)
from .core.save_reader import SaveReader
from .core.save_updates import prepare_update
from .core.scanner import missing_dependencies, run_scan
from .core.state_store import StateStore

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
ASSETS = ROOT / "assets"

CATEGORY_ZH = {
    "steed_appearances": "灵马外观",
    "region": "区域", "world_maps": "地图碎片", "gestures": "肢体动作", "great_runes": "大卢恩",
    # Map / world markers.
    "grace": "赐福", "boss": "Boss", "poi": "地点", "landmark": "地标", "fragment": "地图碎片",
    "mausoleum": "漫步灵庙", "unique_drop": "唯一敌人奖励", "npc": "NPC",
    # Current generated collection categories.
    "crafting_materials": "制作材料", "golden_runes_low": "低阶黄金卢恩", "golden_runes": "黄金卢恩",
    "armaments": "武器", "armour": "防具", "consumables": "消耗品", "smithing_stones_low": "低阶锻造石",
    "smithing_stones": "锻造石", "smithing_stones_rare": "稀有锻造石", "throwables": "投掷道具",
    "greases": "附魔油脂", "talismans": "护符", "stat_boosts": "属性提升道具", "misc": "其他物品",
    "cookbooks": "制作笔记", "ammo": "弹药", "seeds_tears": "种子与圣杯露滴", "stonesword_keys": "石剑钥匙",
    "utilities": "实用道具", "gloveworts": "墓地铃兰", "pots_n_perfumes": "壶与调香瓶",
    "scadutree_fragments": "幽影树碎片", "progression": "流程关键物品", "spirits": "骨灰", "rune_arcs": "卢恩弯弧",
    "incantations": "祷告", "sorceries": "魔法", "bell_bearings": "铃珠", "great_gloveworts": "大朵铃兰",
    "lost_ashes": "失力战灰", "larval_tears": "泪滴幼体", "ashes_of_war": "战灰", "prayerbooks": "祷告书",
    "crystal_tears": "结晶露滴", "celestial_dew": "星星泪滴", "prattling_pates": "唤声泥颅",
    "reusables": "可重复使用道具", "seedbed_curses": "温床的诅咒", "whetblades": "砥石刀",
    "deathroot": "死根", "memory_stones": "记忆石", "mp_fingers": "联机手指道具", "imbued_sword_keys": "魔石剑钥匙",
    "rune_pieces": "符文碎片", "ember_pieces": "余火碎片",
    # Backward-compatible category names from older generated data.
    "weapon": "武器", "armor": "防具", "talisman": "护符", "spell": "魔法/祷告", "ash": "战灰",
    "spirit": "骨灰", "key": "关键物品", "upgrade": "强化材料", "tear": "露滴", "cookbook": "制作笔记",
    "map": "地图碎片", "gesture": "肢体动作", "piece": "碎片", "item": "物品",
}


def load_json(path: Path, fallback):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return fallback


def local_path(value: str) -> str:
    if value.startswith("file:"):
        return QUrl(value).toLocalFile()
    return value


def _surface_status(marker: dict) -> str:
    quality = marker.get("surfaceQuality")
    method = marker.get("surfaceMethod")
    if quality == "exact" and method == "navmesh":
        return "直接导航网格射线"
    if quality == "approx":
        return "邻域导航网格估算"
    return "未知"


class ScanWorker(QObject):
    progress = Signal(int, int, str)
    log = Signal(str)
    done = Signal(dict)
    cancelled = Signal(str)
    failed = Signal(str)
    finished = Signal()

    def __init__(self, selected, mod=""):
        super().__init__()
        self.selected = selected
        self.mod = mod
        self._cancel = False

    @Slot()
    def run(self):
        try:
            manifest = run_scan(
                ROOT, self.selected, self.mod or None,
                self.progress.emit, self.log.emit, lambda: self._cancel,
            )
            self.done.emit(manifest)
        except InterruptedError as exc:
            self.cancelled.emit(str(exc) or "解析已取消")
        except Exception as exc:
            self.failed.emit(str(exc) + "\n" + traceback.format_exc(limit=4))
        finally:
            self.finished.emit()

    @Slot()
    def cancel(self):
        self._cancel = True


class SaveWorker(QObject):
    done = Signal(object, str, object)
    failed = Signal(str)
    finished = Signal()

    def __init__(self, path: Path, mtime_ns: int, context):
        super().__init__()
        self.path = path
        self.mtime_ns = mtime_ns
        self.context = context

    @Slot()
    def run(self):
        try:
            parsed = SaveReader(self.path, DATA / "eventflag_bst.txt").read()
            update = prepare_update(parsed, str(self.path), self.context)
            self.done.emit(update, str(self.path), self.mtime_ns)
        except Exception as exc:
            self.failed.emit(str(exc))
        finally:
            self.finished.emit()


class Backend(QObject):
    setupRequiredChanged = Signal()
    setupReasonChanged = Signal()
    scanChanged = Signal()
    dataChanged = Signal()
    characterChanged = Signal()
    mapChanged = Signal()
    catalogChanged = Signal()
    questsChanged = Signal()
    savePathChanged = Signal()
    contentPacksChanged = Signal()
    displaySettingsChanged = Signal()
    savePollIntervalChanged = Signal()
    dependenciesChanged = Signal()
    toast = Signal(str)
    scanLog = Signal(str)

    def __init__(self):
        super().__init__()
        self.store = StateStore(DATA / "user-state.json")
        self._setup = True
        self._reason = ""
        self._game_dir = ""

        self._scan_running = False
        self._scan_step = 0
        self._scan_total = 1
        self._scan_status = ""
        self._scan_thread = None
        self._scan_worker = None

        self._save_thread = None
        self._save_worker = None
        self._save_pending = False
        self._save_requested_path = ""
        self._save_requested_mtime = 0
        self._save_generation = 0

        self.markers = []
        self.marker_by_id = {}
        self._marker_packs = {}
        self.catalog = {}
        self.catalog_index = build_index({})
        self._icon_cache = {}
        self.quest_doc = {"quests": []}
        self.projector = Projector(None)
        self.characters = []
        self.active_slot = None
        self._auto_found = set()
        self._collection = {"owned": {}}
        self._quest_eval = {"states": {}, "summary": {}}
        self.tile_manifest = {"tileSize": 256, "masterPx": 10496, "masters": {}}
        self.save_path = ""
        self._save_mtime_ns = 0
        self._missing_deps = missing_dependencies()

        # A hard exit during a manual reparse may leave the previous valid cache
        # in the transaction backup. Recover it before deciding whether setup is
        # required, so a power loss/cancel never strands a usable installation.
        recover_interrupted_scan(ROOT)
        status = validate_cache(ROOT)
        self._setup = not status.valid
        self._reason = status.reason
        self._game_dir = status.game_dir
        if status.valid:
            self.reload_data()

        self.timer = QTimer(self)
        self.timer.setInterval(round(self.savePollInterval * 1000))
        self.timer.timeout.connect(self.refresh_save)
        self.timer.start()

    @Property(float, notify=savePollIntervalChanged)
    def savePollInterval(self):
        value = self.store.data["settings"].get("savePollInterval", 1.2)
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            return 1.2
        return max(0.2, min(60.0, float(value)))

    @Property(str, notify=savePathChanged)
    def configuredSavePath(self):
        return str(self.store.data['settings'].get('savePath', ''))

    @Property(str, notify=savePathChanged)
    def currentSavePath(self):
        return self.save_path

    @Property('QVariantMap', notify=contentPacksChanged)
    def contentPacks(self):
        scope = self.save_path or self._game_dir or 'default'
        saved = self.store.data['settings'].get('contentPacks', {}).get(scope, {})
        return {key: saved.get(key) if saved.get(key) in ('show', 'hide') else 'unknown'
                for key in ('dlc', 'tarnished')}

    @Slot(str, str)
    def setContentPack(self, key, state):
        if key not in ('dlc', 'tarnished') or state not in ('unknown', 'show', 'hide'):
            return
        scope = self.save_path or self._game_dir or 'default'
        self.store.data['settings'].setdefault('contentPacks', {}).setdefault(scope, {})[key] = state
        self.store.save()
        self.contentPacksChanged.emit()
        self.dataChanged.emit()
        self.characterChanged.emit()

    def _pack_visible(self, pack):
        key = {'黄金树幽影': 'dlc', '褪色者礼包': 'tarnished'}.get(pack, pack)
        return self.contentPacks.get(key) != 'hide'

    def _marker_visible(self, marker):
        pack = marker.get('contentPack') or marker.get('pack')
        if not pack and marker.get('master') in ('M10', 'M11'):
            pack = 'dlc'
        if not self._pack_visible(pack):
            return False
        packs = self._marker_packs.get(str(marker.get('id')))
        return not packs or any(self._pack_visible(p) for p in packs)

    @Slot(str, result=bool)
    def masterVisible(self, master):
        return master not in ('M10', 'M11') or self._pack_visible('dlc')

    @Slot(float)
    def setSavePollInterval(self, seconds):
        if not math.isfinite(seconds):
            return
        seconds = round(max(0.2, min(60.0, seconds)), 1)
        self.store.data["settings"]["savePollInterval"] = seconds
        self.store.save()
        self.timer.setInterval(round(seconds * 1000))
        self.savePollIntervalChanged.emit()

    @Property(bool, notify=setupRequiredChanged)
    def setupRequired(self):
        return self._setup

    @Property(str, notify=setupReasonChanged)
    def setupReason(self):
        return self._reason

    @Property(str, notify=setupReasonChanged)
    def gameDir(self):
        return self._game_dir

    @Property(bool, notify=scanChanged)
    def scanRunning(self):
        return self._scan_running

    @Property(float, notify=scanChanged)
    def scanProgress(self):
        return self._scan_step / max(1, self._scan_total)

    @Property(str, notify=scanChanged)
    def scanStatus(self):
        return self._scan_status

    @Property(str, notify=dependenciesChanged)
    def missingDependencies(self):
        return ", ".join(self._missing_deps)

    @Property(str, notify=dataChanged)
    def assetsRoot(self):
        return QUrl.fromLocalFile(str(ASSETS.resolve()) + os.sep).toString()

    @Property(int, notify=dataChanged)
    def masterPx(self):
        return int(self.tile_manifest.get("masterPx", 10496))

    @Property("QVariantList", notify=characterChanged)
    def characterList(self):
        return [{k: v for k, v in c.items() if not k.startswith("_")} for c in self.characters]

    @Property(int, notify=characterChanged)
    def activeSlot(self):
        return -1 if self.active_slot is None else int(self.active_slot)

    @Property("QVariantMap", notify=characterChanged)
    def activeCharacter(self):
        c = self._character()
        if not c:
            return {}
        out = {k: v for k, v in c.items() if not k.startswith("_") }
        manual = self.store._bucket(self.save_path, c)
        out["foundCount"] = sum(1 for m in self.markers if self._marker_visible(m) and (str(m.get("id")) in self._auto_found or manual.get(str(m.get("id"))) is True))
        out["collectionDistinct"] = sum(1 for row in self.catalog.get('items', []) if row.get('key') in self._collection.get('owned', {}) and self._pack_visible(content_pack(row)))
        summary = dict.fromkeys(('available', 'active', 'locked', 'completed', 'failed', 'warnings', 'missed'), 0)
        for quest in self.quest_doc.get('quests', []):
            state = self._quest_eval.get('states', {}).get(str(quest.get('id')))
            if state and self._pack_visible(quest.get('pack', 'base')):
                summary[state['status']] += 1
                for risk in state.get('risks', []):
                    summary['missed' if risk['triggered'] else 'warnings'] += 1
        out["questSummary"] = summary
        return out

    @Property("QVariantMap", notify=displaySettingsChanged)
    def displaySettings(self):
        return self.store.display_settings(self.save_path, self._character())

    @Slot(str, bool)
    def setDisplaySetting(self, key, value):
        self.store.set_display_setting(self.save_path, self._character(), key, value)
        self.displaySettingsChanged.emit()

    def _icon_name(self, icon):
        key = (type(icon), str(icon))
        if key not in self._icon_cache:
            self._icon_cache[key] = marker_icon_name(ASSETS, icon)
        return self._icon_cache[key]

    def _set_setup(self, on, reason=None):
        changed = self._setup != on
        self._setup = on
        if reason is not None:
            self._reason = reason
        if changed:
            self.setupRequiredChanged.emit()
        self.setupReasonChanged.emit()

    def _character(self):
        return next(
            (c for c in self.characters if c.get("slot") == self.active_slot),
            self.characters[0] if self.characters else None,
        )

    def _marker_checked(self, ident):
        return self.store.marker_checked(self.save_path, self._character(), str(ident))

    @Slot()
    def reload_data(self):
        self._save_generation += 1
        self._save_mtime_ns = 0
        self._icon_cache.clear()
        marker_doc = load_json(DATA / "markers.json", {"markers": []})
        docs = [
            marker_doc,
            load_json(DATA / "items.json", {"markers": []}),
            load_json(DATA / "unique_drops.json", {"markers": []}),
            load_json(DATA / "mausoleums.json", {"markers": []}),
            load_json(DATA / "pieces.json", {"markers": []}),
        ]
        self.markers = [m for d in docs for m in d.get("markers", [])]
        for marker in self.markers:
            marker["_uiIcon"] = marker_icon_name(ASSETS, marker.get("icon"))
        self.marker_by_id = {str(m.get("id")): m for m in self.markers}
        from .core.tips import tip_text
        tips = load_json(DATA / "tips.json", {"tips": {}}).get("tips", {})
        translations = load_json(DATA / "tips-zh.json", {}).get("translations", {})
        for m in self.markers:
            tip = tips.get(str(m.get("id"))) or m.get("tip")
            if isinstance(tip, dict):
                m["tip"] = {**tip, "text": tip_text(tip, translations)}
        self.catalog = load_json(DATA / "catalog.json", {"schema": 2, "items": [], "categories": {}})
        self.catalog_index = build_index(self.catalog)
        self._marker_packs = {}
        for row in self.catalog.get('items', []):
            for source in row.get('sources', []):
                if source.get('marker'):
                    self._marker_packs.setdefault(str(source['marker']), set()).add(content_pack(row))
        base = load_json(DATA / "quests" / "base_game.json", {"quests": []})
        dlc = load_json(DATA / "quests" / "dlc.json", {"quests": []})
        supplemental = load_json(DATA / "quests" / "supplemental.json", {"quests": []})
        self.quest_doc = {
            "schema": max(base.get("schema", 1), dlc.get("schema", 1)),
            "quests": [
                *[{**q, "pack": q.get("pack", "base")} for q in base.get("quests", [])],
                *[{**q, "pack": q.get("pack", "dlc")} for q in dlc.get("quests", [])],
                *supplemental.get("quests", []),
            ],
        }
        self.projector = Projector(load_json(DATA / "legacy-conv.json", None))
        self.tile_manifest = load_json(ASSETS / "tiles" / "manifest.json", self.tile_manifest)
        status = validate_cache(ROOT)
        self._game_dir = status.game_dir
        self.setupReasonChanged.emit()
        self.dataChanged.emit()
        self.refresh_save(force=True)

    @Slot(str, str)
    def startScan(self, selected, mod_dir=""):
        if self._scan_running:
            return
        self._missing_deps = missing_dependencies()
        self.dependenciesChanged.emit()
        try:
            gd = normalize_game_dir(local_path(selected))
            self._game_dir = str(gd)
        except Exception as exc:
            self._set_setup(True, str(exc))
            return
        self._scan_running = True
        self._scan_step = 0
        self._scan_total = 1
        self._scan_status = "准备解析"
        self.scanChanged.emit()
        thread = QThread(self)
        worker = ScanWorker(str(gd), local_path(mod_dir) if mod_dir else "")
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.progress.connect(self._on_scan_progress)
        worker.log.connect(self.scanLog.emit)
        worker.done.connect(self._on_scan_done)
        worker.cancelled.connect(self._on_scan_cancelled)
        worker.failed.connect(self._on_scan_failed)
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(self._scan_thread_finished)
        self._scan_thread = thread
        self._scan_worker = worker
        thread.start()

    @Slot()
    def cancelScan(self):
        if self._scan_worker:
            self._scan_worker.cancel()

    @Slot(int, int, str)
    def _on_scan_progress(self, i, total, status):
        self._scan_step = i
        self._scan_total = total
        self._scan_status = status
        self.scanChanged.emit()

    @Slot(dict)
    def _on_scan_done(self, manifest):
        self._game_dir = str(manifest.get("game_dir", ""))
        self._missing_deps = missing_dependencies()
        self.dependenciesChanged.emit()
        self._set_setup(False, "解析缓存有效")
        self.reload_data()
        self.toast.emit("游戏资源解析完成")

    @Slot(str)
    def _on_scan_cancelled(self, msg):
        self._missing_deps = missing_dependencies()
        self.dependenciesChanged.emit()
        status = validate_cache(ROOT)
        if status.valid:
            self._game_dir = status.game_dir
            self._set_setup(False, status.reason)
            self.reload_data()
        else:
            self._set_setup(True, "解析已取消")
        self._scan_status = "解析已取消"
        self.scanLog.emit(msg or "解析已取消")
        self.toast.emit("解析已取消")

    @Slot(str)
    def _on_scan_failed(self, msg):
        self._missing_deps = missing_dependencies()
        self.dependenciesChanged.emit()
        status = validate_cache(ROOT)
        if status.valid:
            self._game_dir = status.game_dir
            self._set_setup(False, "重新解析失败，已保留上一份有效缓存")
            self.reload_data()
            self.toast.emit("重新解析失败，已恢复上一份有效缓存")
        else:
            self._set_setup(True, "解析失败")
            self.toast.emit("解析失败，请查看日志")
        self.scanLog.emit(msg)

    @Slot()
    def _scan_thread_finished(self):
        self._scan_running = False
        self._scan_thread = None
        self._scan_worker = None
        self.scanChanged.emit()

    @Slot()
    def clearScanCache(self):
        if self._scan_running:
            return
        clear_scan_cache(ROOT)
        self._game_dir = ""
        self.markers = []
        self.marker_by_id = {}
        self.characters = []
        self.active_slot = None
        self._set_setup(True, "解析缓存已清理")
        self.displaySettingsChanged.emit()
        self.dataChanged.emit()
        self.characterChanged.emit()

    @Slot()
    def reparse(self):
        self._set_setup(True, "已进入手动重新解析模式")

    @Slot()
    def keepCurrentCache(self):
        status = validate_cache(ROOT)
        if status.valid:
            self._game_dir = status.game_dir
            self._set_setup(False, status.reason)
            self.reload_data()
        else:
            self._set_setup(True, status.reason)

    def _find_save(self):
        configured = self.store.data.get("settings", {}).get("savePath")
        if configured:
            return Path(configured)
        try:
            from tools.erlib.gamepath import find_save
            p = find_save()
            return Path(p) if p else None
        except Exception:
            return None

    @Slot(str)
    def setSavePath(self, value):
        value = local_path(value.strip().strip('"'))
        if not value:
            self.store.data['settings'].pop('savePath', None)
            self.store.save()
            self._save_generation += 1
            self.savePathChanged.emit()
            self.refresh_save(force=True)
            return
        p = Path(value).expanduser().resolve()
        if not p.is_file():
            self.toast.emit("存档文件不存在")
            return
        try:
            with p.open('rb') as stream:
                if stream.read(4) != b'BND4':
                    self.toast.emit('所选文件不是支持的 Elden Ring 存档')
                    return
        except OSError as exc:
            self.toast.emit(f'无法读取存档：{exc}')
            return
        self.store.data["settings"]["savePath"] = str(p)
        self.store.save()
        self._save_generation += 1
        self.savePathChanged.emit()
        self._save_mtime_ns = 0
        self.refresh_save(force=True)

    @Slot(int)
    def setActiveSlot(self, slot):
        if slot == self.active_slot:
            return
        if not any(c.get("slot") == slot for c in self.characters):
            return
        self.active_slot = slot
        self._save_generation += 1
        if self.save_path:
            self.store.data["slots"][self.save_path] = slot
            self.store.save()
        self._recompute_character()
        self.displaySettingsChanged.emit()
        self.characterChanged.emit()
        self.dataChanged.emit()

    @Slot()
    @Slot(bool)
    def refresh_save(self, force=False):
        if self._setup or self._scan_running:
            return
        p = self._find_save()
        if not p:
            return
        try:
            mtime = p.stat().st_mtime_ns
        except OSError:
            return
        if not force and str(p) == self.save_path and mtime == self._save_mtime_ns:
            return
        if self._save_thread is not None:
            if force or str(p) != self._save_requested_path or mtime != self._save_requested_mtime:
                self._save_pending = True
            return

        self._save_requested_path = str(p)
        self._save_requested_mtime = mtime
        thread = QThread(self)
        store_snapshot = copy.copy(self.store)
        store_snapshot.data = copy.deepcopy(self.store.data)
        context = dict(store=store_snapshot, path=self.save_path, slot=self.active_slot,
                       force=self._save_mtime_ns == 0,
                       characters=[dict(c) for c in self.characters], generation=self._save_generation,
                       found=self._auto_found, collection=self._collection, quests=self._quest_eval,
                       markers=self.markers, catalog=self.catalog, index=self.catalog_index,
                       quest_doc=self.quest_doc, projector=self.projector)
        worker = SaveWorker(p, mtime, context)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.done.connect(self._on_save_done)
        worker.failed.connect(self._on_save_failed)
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(self._save_thread_finished)
        self._save_thread = thread
        self._save_worker = worker
        thread.start()

    @Slot(object, str, object)
    def _on_save_done(self, parsed, path, mtime):
        if self._setup:
            return
        if parsed['generation'] != self._save_generation:
            self._save_pending = True
            return
        self.characters = parsed['characters']
        path_changed = self.save_path != path
        self.save_path = path
        self._save_mtime_ns = int(mtime)
        self.active_slot = parsed['slot']
        self._auto_found = parsed['found']
        self._collection = parsed['collection']
        self._quest_eval = parsed['quests']
        if path_changed:
            self.savePathChanged.emit()
            self.contentPacksChanged.emit()
        if parsed['identity']:
            self.displaySettingsChanged.emit()
        if parsed['character_changed']:
            self.characterChanged.emit()
        if parsed['map_changed']:
            self.mapChanged.emit()
        if parsed['catalog_changed']:
            self.catalogChanged.emit()
        if parsed['quests_changed']:
            self.questsChanged.emit()

    @Slot(str)
    def _on_save_failed(self, msg):
        # The game can rewrite the save while the polling timer fires. Keep the
        # last good snapshot instead of blocking the UI or replacing it with a
        # torn one. Surface the error only when no usable snapshot exists yet.
        if not self.characters:
            self.toast.emit(f"存档读取失败：{msg}")

    @Slot()
    def _save_thread_finished(self):
        self._save_thread = None
        self._save_worker = None
        pending = self._save_pending
        self._save_pending = False
        if pending and not self._setup:
            QTimer.singleShot(0, lambda: self.refresh_save(True))

    def _recompute_character(self):
        c = self._character()
        self._auto_found = set()
        self._collection = {"owned": {}}
        if not c or not c.get("ok"):
            self._quest_eval = evaluate_document(self.quest_doc, c or {}, (), None)
            return
        flags = c.get("_flags")
        for marker in self.markers:
            ids = marker.get("flags") or ([marker.get("flag")] if marker.get("flag") else [])
            if ids and any(flags.get(flag) is True for flag in ids):
                self._auto_found.add(str(marker.get("id")))
        self._collection = resolve_catalog(self.catalog_index, c.get("_inventoryRaw"), c.get("_gestureIds", []))
        # Map pieces may disappear from inventory. Use persistent game flags,
        # linked by goods Param acquisition flag, never by translated names.
        for row in self.catalog.get("items", []):
            if row.get("category") != "world_maps":
                continue
            acquired = any(flags.get(int(f)) is True for f in row.get("acquisitionFlags", []) if f) if flags else False
            if not acquired:
                acquired = any(str(src.get("marker")) in self._auto_found for src in row.get("sources", []))
            if acquired:
                self._collection["owned"].setdefault(row["key"], {"quantity": 1, "held": 0, "storage": 0})
        self._collection["distinct"] = len(self._collection["owned"])
        self._quest_eval = evaluate_document(
            self.quest_doc, c, self._auto_found,
            lambda q, s: self.store.quest_done(self.save_path, c, q, s),
        )
        if c.get("position"):
            c["mapPixel"] = self.projector.project(c["position"])

    def _is_found(self, ident):
        ident = str(ident)
        return ident in self._auto_found or self._marker_checked(ident)

    @Slot(str, bool)
    def setMarkerChecked(self, ident, value):
        c = self._character()
        if not c:
            self.toast.emit("请先选择一个存档角色，再记录手动收集状态")
            return
        self.store.set_marker_checked(self.save_path, c, ident, value)
        self._save_generation += 1
        self.mapChanged.emit()
        self.characterChanged.emit()

    @Slot(result=int)
    def importLegacyMarkerChecks(self):
        c = self._character()
        if not c:
            self.toast.emit("请先选择要导入到的角色")
            return 0
        count = self.store.import_legacy_markers(self.save_path, c, self.marker_by_id.keys())
        self.toast.emit(f"已向当前角色导入 {count} 个旧版共享勾选" if count else "没有可导入的新旧版共享勾选")
        if count:
            self._save_generation += 1
            self.mapChanged.emit(); self.characterChanged.emit()
        return count

    @Slot(result=int)
    def legacyMarkerCount(self):
        return len(self.store.legacy_marker_ids(self.marker_by_id.keys()))

    @Slot(str, str, bool)
    def setQuestStepChecked(self, qid, sid, value):
        c = self._character()
        if not c:
            return
        quest = next((q for q in self.quest_doc.get("quests", []) if str(q.get("id")) == qid), {})
        step = next((s for s in quest.get("steps", []) if str(s.get("id")) == sid), {})
        if not (step.get("guideOnly") or step.get("manual") is True):
            return
        if value and step.get("exclusiveGroup") and step.get("exclusiveOption"):
            for other in quest.get("steps", []):
                if (other.get("exclusiveGroup") == step["exclusiveGroup"]
                        and other.get("exclusiveOption") != step["exclusiveOption"]):
                    self.store.set_quest_done(self.save_path, c, qid, str(other.get("id")), False)
        self.store.set_quest_done(self.save_path, c, qid, sid, value)
        self._save_generation += 1
        self._quest_eval = evaluate_document(
            self.quest_doc, c, self._auto_found,
            lambda q, s: self.store.quest_done(self.save_path, c, q, s),
        )
        self.characterChanged.emit()
        self.questsChanged.emit()

    @Slot(result="QVariantList")
    def categoryList(self):
        counts = {}
        for marker in self.markers:
            if not self._marker_visible(marker):
                continue
            cat = str(marker.get("cat", "item"))
            counts[cat] = counts.get(cat, 0) + 1
        return [
            {"id": key, "name": CATEGORY_ZH.get(key, key), "count": value}
            for key, value in sorted(counts.items(), key=lambda item: CATEGORY_ZH.get(item[0], item[0]))
        ]

    def shutdown(self):
        """Stop background work before Qt destroys its QThread wrappers."""
        self.timer.stop()
        scan_worker = self._scan_worker
        scan_thread = self._scan_thread
        if scan_worker is not None:
            scan_worker.cancel()
        if scan_thread is not None and scan_thread.isRunning():
            scan_thread.quit()
            scan_thread.wait()
        save_thread = self._save_thread
        if save_thread is not None and save_thread.isRunning():
            save_thread.quit()
            save_thread.wait()

    @Slot(str, float, float, float, float, float, str, str, bool, result="QVariantList")
    def visibleMarkers(self, master, zoom, left, top, right, bottom, query="", categories="", hide_found=False):
        cats = {x for x in categories.split(",") if x}
        q = query.strip().lower()
        try:
            zoom_value = float(zoom)
        except (TypeError, ValueError):
            zoom_value = 1.0
        if not math.isfinite(zoom_value) or zoom_value <= 0:
            zoom_value = 1.0
        pad = 120 / max(zoom_value, 0.08)
        rows = []
        character = self._character()
        manual_checks = self.store._bucket(self.save_path, character) if character else {}
        for marker in self.markers:
            if not self._marker_visible(marker):
                continue
            if str(marker.get("master", "M00")) != master:
                continue
            try:
                x = float(marker.get("px")); y = float(marker.get("py"))
            except (TypeError, ValueError):
                continue
            if not math.isfinite(x) or not math.isfinite(y):
                continue
            if x < left - pad or x > right + pad or y < top - pad or y > bottom + pad:
                continue
            if cats and str(marker.get("cat")) not in cats:
                continue
            ident = str(marker.get("id"))
            manual = manual_checks.get(ident) is True
            found = ident in self._auto_found or manual
            if hide_found and found:
                continue
            name = local_text(marker.get("names") or marker.get("name"), "zh")
            if q and q not in name.lower() and q not in ident.lower():
                continue
            icon_name = str(marker.get("_uiIcon") or "")
            rows.append({
                "id": ident, "x": x, "y": y, "h": marker.get("h"),
                "surfaceDelta": marker.get("surfaceDelta"),
                "surfaceMethod": marker.get("surfaceMethod"),
                "surfaceQuality": marker.get("surfaceQuality"),
                "surfaceStatus": _surface_status(marker),
                "cat": str(marker.get("cat", "item")), "name": name or ident,
                "found": found, "manual": manual, "icon": icon_name,
                "tip": ((marker.get("tip") or {}).get("text") if isinstance(marker.get("tip"), dict) else ""),
                "cluster": False, "count": 1,
            })

        # At overview zoom, a few thousand QML marker delegates are unnecessary.
        # Cluster in world space to roughly 56 screen pixels per group. Search
        # results stay unclustered so an explicit query always identifies items.
        if not q and (zoom_value < 0.45 or len(rows) > 800) and len(rows) > 160:
            cell = 56.0 / max(zoom_value, 0.04)
            groups = {}
            for row in rows:
                if row["cat"] == "boss":
                    continue
                key = (int(row["x"] // cell), int(row["y"] // cell), row["found"])
                groups.setdefault(key, []).append(row)
            clustered = [row for row in rows if row["cat"] == "boss"]
            for key, group in groups.items():
                if len(group) == 1:
                    clustered.append(group[0]); continue
                clustered.append({
                    "id": f"__cluster__:{master}:{key[0]}:{key[1]}:{int(key[2])}",
                    "x": sum(r["x"] for r in group) / len(group),
                    "y": sum(r["y"] for r in group) / len(group),
                    "name": f"{len(group)} 个标记",
                    "cat": "cluster", "found": all(r["found"] for r in group),
                    "manual": False, "icon": "", "tip": "",
                    "cluster": True, "count": len(group),
                    "surfaceDelta": None, "surfaceMethod": None,
                    "surfaceQuality": None, "surfaceStatus": "",
                })
            rows = clustered
        return rows

    @Slot(str, result="QVariantList")
    def baseTiles(self, master):
        return self.visibleTiles(master, 0.0625, 0, 0, self.masterPx, self.masterPx)

    @Slot(str, float, float, float, float, float, result="QVariantList")
    def visibleTiles(self, master, zoom, left, top, right, bottom):
        if not self.masterVisible(master):
            return []
        info = (self.tile_manifest.get("masters") or {}).get(master) or {}
        if not info:
            return []
        native = int(info.get("nativeZoom", 6))
        fmt = self.tile_manifest.get("format", "webp")
        tile = int(self.tile_manifest.get("tileSize", 256))
        try:
            zoom_value = float(zoom)
        except (TypeError, ValueError):
            zoom_value = 1.0
        if not math.isfinite(zoom_value) or zoom_value <= 0:
            zoom_value = 1.0
        level = max(0, min(native, native + math.floor(math.log2(max(zoom_value, 0.001)))))
        logical = tile * (2 ** (native - level))
        existing = {tuple(x) for x in (info.get("tiles") or {}).get(str(level), [])}
        if not existing:
            return []
        x0 = max(0, int(math.floor(left / logical)) - 1)
        y0 = max(0, int(math.floor(top / logical)) - 1)
        x1 = int(math.ceil(right / logical)) + 1
        y1 = int(math.ceil(bottom / logical)) + 1
        base = ASSETS / "tiles" / master / str(level)
        cx = (left + right) / 2; cy = (top + bottom) / 2
        candidates = []
        for x in range(x0, x1 + 1):
            for y in range(y0, y1 + 1):
                if existing and (x, y) not in existing:
                    continue
                p = base / str(x) / f"{y}.{fmt}"
                distance = (x * logical + logical / 2 - cx) ** 2 + (y * logical + logical / 2 - cy) ** 2
                candidates.append((distance, x, y, p))
        candidates.sort(key=lambda row: row[0])
        # Safety cap: with mip selection normal viewports are far below this,
        # but a malformed manifest or huge virtual screen cannot create an
        # unbounded number of Image delegates.
        out = []
        for _, x, y, p in candidates[:96]:
            out.append({
                "x": x * logical, "y": y * logical, "size": logical,
                "source": QUrl.fromLocalFile(str(p.resolve())).toString(), "level": level,
            })
        return out

    @Slot(str, str, str, result="QVariantList")
    def questCards(self, status_filter="all", query="", pack="all"):
        qtext = query.strip().lower(); states = self._quest_eval.get("states", {}); out = []
        for quest in self.quest_doc.get("quests", []):
            if not self._pack_visible(quest.get('pack', 'base')):
                continue
            state = states.get(str(quest.get("id")), {"status": "locked", "steps": [], "risks": []})
            status = state.get("status", "locked")
            if status_filter != "all" and status != status_filter and not (status_filter == "risk" and state.get("risks")) and not (status_filter == "todo" and status in {"active", "available"}):
                continue
            if pack != "all" and quest.get("pack", "base") != pack:
                continue
            name = local_text(quest.get("name"), "zh"); char = local_text(quest.get("character"), "zh")
            if qtext and qtext not in (name + " " + char).lower() and not any(qtext in " ".join(local_text(s.get(k), "zh") for k in ("title", "action", "reward")).lower() for s in quest.get("steps", [])):
                continue
            evaluated = {str(x.get("id")): x for x in state.get("steps", [])}; steps = []
            for step in quest.get("steps", []):
                ev = evaluated.get(str(step.get("id")), {})
                steps.append({
                    "id": str(step.get("id")), "questId": str(quest.get("id")),
                    "title": local_text(step.get("title"), "zh"), "action": local_text(step.get("action"), "zh"),
                    "reward": local_text(step.get("reward"), "zh"), "state": ev.get("state", "future"),
                    "guideOnly": bool(step.get("guideOnly")), "source": ev.get("source") or "",
                    "complete": bool(ev.get("complete")), "manualEligible": bool(step.get("guideOnly") or step.get("manual")),
                    "manual": bool(ev.get("manual")), "optional": bool(step.get("optional")),
                    "anchor": (step.get("anchor") or {}).get("marker", ""),
                })
            risk_defs = {str(r.get("id")): r for r in (quest.get("lockouts") or [])}
            risks = []
            for risk in state.get("risks", []):
                rule = risk_defs.get(str(risk.get("id")), {})
                risks.append({
                    **risk,
                    "text": local_text(rule.get("text"), "zh"),
                })
            out.append({
                "id": str(quest.get("id")), "name": name, "character": char,
                "pack": quest.get("pack", "base"), "status": status,
                "current": state.get("current", []), "risks": risks, "steps": steps,
                "nextAction": next((s["title"] for s in steps if s["state"] == "available"), ""),
                "doneCount": sum(s["complete"] for s in steps), "stepCount": len(steps),
                "progress": f"{state.get('resolvedCount', 0)}/{state.get('stepCount', len(steps))}",
            })
        rank = {"active": 0, "available": 1, "failed": 2, "locked": 3, "completed": 4}
        out.sort(key=lambda x: (rank.get(x["status"], 9), x["name"]))
        return out

    @Slot(result="QVariantList")
    def catalogCategories(self):
        categories = {collection_category(row) for row in self.catalog.get("items", [])
                      if is_collectible(row) and self._pack_visible(content_pack(row))}
        preferred = ["armaments", "armour", "ashes_of_war", "sorceries", "incantations", "talismans", "spirits"]
        ordered = [cat for cat in preferred if cat in categories]
        ordered.extend(sorted(categories - set(ordered), key=lambda cat: CATEGORY_ZH.get(cat, cat)))
        return [{"id": "all", "name": "全部"}] + [{"id": cat, "name": CATEGORY_ZH.get(cat, cat)} for cat in ordered]

    @Slot(str, str, bool, result="QVariantList")
    def catalogItems(self, category="all", query="", missing_only=False):
        primary = {"armaments", "armour", "ashes_of_war", "sorceries", "incantations", "talismans", "spirits"}
        owned = self._collection.get("owned", {}); q = query.strip().lower(); out = []
        for row in self.catalog.get("items", []):
            if not self._pack_visible(content_pack(row)):
                continue
            cat = collection_category(row)
            name = local_text(row.get("names") or row.get("name"), "zh")
            names = row.get("names") or {"name": name}
            if not name or any("[error]" in str(n).lower() or "%null%" in str(n).lower() for n in names.values()):
                continue
            if not is_collectible(row):
                continue
            if category == "other" and cat in primary:
                continue
            if category not in ("all", "other") and cat != category:
                continue
            key = row.get("key") or f"{row.get('type')}:{row.get('id')}"
            have = owned.get(key); is_owned = have is not None
            if missing_only and is_owned:
                continue
            if q and q not in (name + " " + content_pack(row) + " " + CATEGORY_ZH.get(cat, cat)).lower() and q not in str(row.get("id", "")):
                continue
            item_icon = self._icon_name(row.get("itemIcon"))
            icon = item_icon or self._icon_name(row.get("icon")) or "categories/anon.png"
            sources = []
            for src in row.get("sources", []):
                marker = self.marker_by_id.get(str(src.get("marker")), {})
                label = local_text(marker.get("names"), "zh")
                kind = {"pickup": "地图拾取", "unique_drop": "唯一敌人 / 脚本奖励", "enemy_drop": "敌人掉落", "map_reward": "地图 / 脚本奖励"}.get(src.get("kind"), src.get("kind", "来源"))
                enemy = str(src.get("enemyName") or "")
                sources.append({"text": kind + (" · " + enemy if enemy else "") + (" · " + label if label else "") + (" · " + str(src["map"]) if src.get("map") else ""), "marker": str(src.get("marker") or "") if marker else ""})
            out.append({
                "key": key, "name": name, "category": cat, "categoryName": CATEGORY_ZH.get(cat, cat), "owned": is_owned,
                "quantity": 0 if not have else have.get("quantity", 0), "id": row.get("id"),
                "icon": icon, "description": local_text(row.get("descriptions"), "zh"),
                "sources": sources, "pack": content_pack(row), "details": row.get("details", {}),
                "iconFallback": not bool(item_icon),
            })
        out.sort(key=lambda row: not row["owned"])
        return out

    @Slot(str, result="QVariantMap")
    def markerDetails(self, ident):
        marker = self.marker_by_id.get(str(ident), {})
        if not self._marker_visible(marker):
            return {}
        cat = str(marker.get("cat", ""))
        return {
            "id": str(ident), "name": local_text(marker.get("names") or marker.get("name"), "zh"),
            "cat": cat, "catName": CATEGORY_ZH.get(cat, cat), "h": marker.get("h"),
            "surfaceDelta": marker.get("surfaceDelta"), "surfaceMethod": marker.get("surfaceMethod"),
            "surfaceQuality": marker.get("surfaceQuality"), "surfaceStatus": _surface_status(marker),
            "map": marker.get("map", ""), "found": self._is_found(ident), "manual": self._marker_checked(ident),
            "tip": ((marker.get("tip") or {}).get("text") if isinstance(marker.get("tip"), dict) else ""),
            "px": marker.get("px"), "py": marker.get("py"), "master": marker.get("master", "M00"),
        }
