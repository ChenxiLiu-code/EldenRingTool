from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from urllib.parse import quote

from .resource_cache import atomic_json


class StateStore:
    """Local-only UI state.

    Legacy versions stored every manual map checkbox in ``checked``. Native 2.x
    keeps that dictionary untouched as an import source, while new map checks are
    scoped to account/save + slot + character name so one character cannot mark
    another character's map complete by accident.
    """

    QUEST_PREFIX = "queststep:"

    def __init__(self, path: Path):
        self.path = path
        try:
            self.data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            self.data = {}
        if not isinstance(self.data, dict):
            self.data = {}
        self.data.setdefault("checked", {})          # legacy shared checks + legacy quest checks
        self.data.setdefault("characterChecked", {}) # native per-character map checks
        self.data.setdefault("questChecked", {})     # native account+character quest confirmations
        self.data.setdefault("slots", {})
        self.data.setdefault("settings", {})
        self.data.setdefault("characterSettings", {})
        self.data.setdefault("questLegacyDisabled", {})
        for key in ("checked", "characterChecked", "questChecked", "slots", "settings", "characterSettings", "questLegacyDisabled"):
            if not isinstance(self.data.get(key), dict):
                self.data[key] = {}

    def save(self):
        atomic_json(self.path, self.data)

    def display_settings(self, save_path, character):
        defaults = {"mapHideCompleted": True, "catalogHideCompleted": False}
        if character:
            saved = self.data["characterSettings"].get(self.character_scope(save_path, character), {})
            if isinstance(saved, dict):
                defaults.update({k: v for k, v in saved.items() if k in defaults and isinstance(v, bool)})
        return defaults

    def set_display_setting(self, save_path, character, key, value):
        if not character or key not in ("mapHideCompleted", "catalogHideCompleted"):
            return
        scope = self.character_scope(save_path, character)
        settings = self.display_settings(save_path, character)
        settings[key] = bool(value)
        self.data["characterSettings"][scope] = settings
        self.save()

    @staticmethod
    def character_token(character):
        return f"{int(character.get('slot', -1))}:{quote(str(character.get('name', '')), safe='')}"

    @staticmethod
    def account_token(save_path: str | Path | None) -> str:
        if not save_path:
            return "unknown"
        p = Path(save_path)
        # Steam saves normally live in .../EldenRing/<SteamID>/ER0000.sl2.
        # Parent directory is therefore the useful account discriminator. For
        # unusual layouts keep a stable, human-readable fallback.
        parent = p.parent.name.strip() or p.stem
        return quote(parent, safe="")

    def character_scope(self, save_path, character):
        return f"{self.account_token(save_path)}:{self.character_token(character)}"

    def _bucket(self, save_path, character, create=False):
        scope = self.character_scope(save_path, character)
        all_buckets = self.data["characterChecked"]
        bucket = all_buckets.get(scope)
        if not isinstance(bucket, dict):
            if not create:
                return {}
            bucket = {}
            all_buckets[scope] = bucket
        return bucket

    def marker_checked(self, save_path, character, ident):
        if not character:
            return False
        return self._bucket(save_path, character).get(str(ident)) is True

    def set_marker_checked(self, save_path, character, ident, value):
        if not character:
            raise ValueError("未选择存档角色")
        ident = str(ident)
        bucket = self._bucket(save_path, character, create=True)
        if value:
            bucket[ident] = True
        else:
            bucket.pop(ident, None)
        self.save()

    def legacy_marker_ids(self, valid_ids=None):
        valid = set(map(str, valid_ids)) if valid_ids is not None else None
        out = []
        for ident, value in self.data["checked"].items():
            ident = str(ident)
            if value is not True or ident.startswith(self.QUEST_PREFIX):
                continue
            if valid is None or ident in valid:
                out.append(ident)
        return out

    def import_legacy_markers(self, save_path, character, valid_ids):
        if not character:
            raise ValueError("未选择存档角色")
        bucket = self._bucket(save_path, character, create=True)
        count = 0
        for ident in self.legacy_marker_ids(valid_ids):
            if bucket.get(ident) is not True:
                bucket[ident] = True
                count += 1
        if count:
            self.save()
        return count

    # Browser-era quest confirmations used only slot + character name, which can
    # collide across Steam accounts. New writes are account/save scoped; the old
    # key is retained as a read-only fallback so existing confirmations survive
    # the migration.
    def quest_id(self, character, qid, sid):
        return f"{self.QUEST_PREFIX}{self.character_token(character)}:{quote(str(qid), safe='')}:{quote(str(sid), safe='')}"

    @staticmethod
    def _quest_step_id(qid, sid):
        return f"{quote(str(qid), safe='')}:{quote(str(sid), safe='')}"

    def _quest_bucket(self, save_path, character, create=False):
        scope = self.character_scope(save_path, character)
        bucket = self.data["questChecked"].get(scope)
        if not isinstance(bucket, dict):
            if not create:
                return {}
            bucket = {}
            self.data["questChecked"][scope] = bucket
        return bucket

    def quest_done(self, save_path, character, qid, sid):
        step = self._quest_step_id(qid, sid)
        if self._quest_bucket(save_path, character).get(step) is True:
            return True
        if self.data["questLegacyDisabled"].get(self.character_scope(save_path, character)):
            return False
        return self.data["checked"].get(self.quest_id(character, qid, sid)) is True

    def reset_manual_marks(self, save_path, character):
        if not character or not save_path:
            raise ValueError("请先选择存档角色")
        scope = self.character_scope(save_path, character)
        previous = deepcopy(self.data)
        self.data["characterChecked"].pop(scope, None)
        self.data["questChecked"].pop(scope, None)
        # Disable legacy fallback for this account/character only. The old
        # shared keys may still be used by another account with the same name.
        self.data["questLegacyDisabled"][scope] = True
        try:
            self.save()
        except Exception:
            self.data = previous
            raise

    def set_quest_done(self, save_path, character, qid, sid, value):
        step = self._quest_step_id(qid, sid)
        bucket = self._quest_bucket(save_path, character, create=True)
        if value:
            bucket[step] = True
        else:
            bucket.pop(step, None)
            # If this exact confirmation came from the legacy store, clearing it
            # must also clear the fallback or the checkbox would immediately
            # appear selected again.
            self.data["checked"].pop(self.quest_id(character, qid, sid), None)
        self.save()
