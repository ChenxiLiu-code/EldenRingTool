"""Extract one-time enemy/script rewards missing from Treasure MSB events.

The original ``extract_items.py`` intentionally starts at MSB Treasure events,
so anything awarded by killing an enemy is absent.  This extractor fills that
hole without adding ordinary farmable drops:

1. MSB Enemy -> NpcParam -> ItemLotParam_map/enemy, but only lots with a
   persistent ``getItemFlagId`` (ordinary random/farmable lots normally have 0)
   *and* an explicitly hostile NpcParam ``teamType``.  Friendly/neutral NPC death
   drops are excluded.  Merchant Bell Bearings are the one deliberate exception.
2. EMEVD one-time reward templates (scarabs, strong enemies, bosses, invasions,
   hostile NPCs, larval-tear mimics).  For 90005300/301 and the boss/hostile-NPC
   templates the *kill flag from the event call* is used instead of the lot
   flag; those templates award the lot directly and the lot flag is not the
   reliable completion signal.

The dropped item's *real item category* is kept.  A scarab that gives an Ash of
War is therefore ``ashes_of_war`` + ``ash.png``, a talisman-dropping enemy is
``talismans`` + ``talisman.png``, etc.  There is deliberately no generic
"enemy drop" category/icon.

    python tools/extract_unique_drops.py -> data/unique_drops.json
"""
from __future__ import annotations

import argparse
import json
import os
import struct
import sys
import time
from collections import Counter, defaultdict

reconfigure = getattr(sys.stdout, "reconfigure", None)
if reconfigure:
    # This script is normally launched with stdout=PIPE by the QML frontend.
    # Force every progress line through immediately instead of block-buffering
    # several minutes of work.
    reconfigure(encoding="utf-8", line_buffering=True, write_through=True)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from erlib import dcx, emevd, fmg, msb as msblib, oodle, param, paramdef
import erlib.mfg_categories as mfg_categories
import erlib.modfiles as modfiles
from erlib.dvdbnd import DvdBnd
from erlib.gamepath import require_game_dir
from build_markers import LegacyConv, LOCALES, place

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFS = os.path.join(ROOT, "data", "paramdefs")

# MSBE Part common layout (Elden Ring / MSBE).
PART_TYPE = 0x0C
PART_MODEL_INDEX = 0x14
PART_POSITION = 0x20
PART_GAME_EDITION_DISABLE = 0x44
PART_ENTITY_DATA_PTR = 0x60
PART_TYPE_DATA_PTR = 0x68
PART_TYPE_ENEMY = 2
ENTITY_ID = 0x00
ENEMY_NPC_PARAM_ID = 0x0C

# NpcParam offsets for Elden Ring's NPC_PARAM_ST.  itemLotId_enemy/map are
# 0x30/0x34; teamType is 0x133 in the current ER Paramdex layout.  Keeping the
# offsets here avoids bundling the ~100 KB NpcParam paramdef only for three
# fields.  The row-size guard below makes a shorter/incompatible layout fail
# safely instead of silently classifying arbitrary bytes as a team.
NPC_ITEM_LOT_ENEMY = 0x30
NPC_ITEM_LOT_MAP = 0x34
NPC_TEAM_TYPE = 0x133

# TeamType values are the Elden Ring EMEVD TeamType enum.  Direct NpcParam
# death-lot discovery is intentionally conservative: only characters whose
# *base* team is unambiguously hostile are admitted.  Scripted EMEVD rewards
# below are not subject to this filter because the relevant common event is
# itself authoritative evidence that this placement is a combat reward.
#
# This is what prevents Patches/Corhyn/Alexander/Miriel/etc. from becoming
# "required" collection markers merely because murdering them can drop an item.
DIRECT_HOSTILE_TEAMS = frozenset({
    3,   # BlackPhantom
    6,   # Enemy
    7,   # StrongEnemy / boss team
    9,   # HostileAlly
    10,  # DecoyEnemy
    13,  # Invader
    16, 17, 18,  # legacy/unused invader slots retained by the enum
    21,  # Hostile
    23,  # Enemy1
    24,  # Enemy2
    25,  # StrongEnemy2
    27,  # HostileNPC
    29,  # Indiscriminate
    32,  # RedBerserker
    33,  # ArchEnemyTeam
})

FRIENDLY_TEAM_TYPES = frozenset({
    1,   # Human/player-like
    2,   # WhitePhantom
    4,   # GrayPhantom
    5,   # WanderingPhantom
    8,   # Ally
    12,  # BattleAlly
    14,  # Neutral
    15,  # Charmed
    19,  # Host
    20,  # Coop
    22,  # WanderingPhantom2
    26,  # FriendlyNPC
    28,  # CoopNPC
    31,  # WhiteBerserker
})

CATEGORY_TABLES = {
    1: "GoodsName",
    2: "WeaponName",
    3: "ProtectorName",
    4: "AccessoryName",
    5: "GemName",
}

# event id -> (lot byte offset, minimum arg length)
# Offsets are instruction-ArgData offsets, i.e. they include the 8-byte
# [slot,eventId] Initialize(Common)Event prefix.  We intentionally do NOT
# hard-code an EntityID offset here: the common-event templates do not all put
# their character/entity parameter in the same place, and some signatures have
# changed between tooling notes.  The EntityID is instead identified from the
# call arguments by intersecting them with the EntityIDs actually present in
# the scanned MSBs, then preferring the placement owned by the caller map.
#
# The lot offsets below are the award-lot parameters of the item-awarding
# templates.  We keep only combat/enemy-like one-time rewards so this extractor
# does not turn into a general quest-reward scanner.
TEMPLATE_EVENTS = {
    90005300: (16, 20),   # scarab / strong-enemy drop
    90005301: (16, 20),
    90005860: (24, 28),   # field/dungeon boss reward variants
    90005861: (24, 28),
    90005880: (24, 28),
    90005774: (12, 16),   # invasion reward
    90005792: (24, 28),   # hostile NPC defeat
    90005390: (28, 32),   # larval-tear / morph enemy reward
}

# X0_4 / caller args@8 is the real kill/completion flag for these templates.
# In particular 90005300/301 award the lot directly; using ItemLot.getItemFlagId
# leaves scarab markers visible after the scarab has already been killed.
CALLER_KILL_FLAG_EVENTS = {90005300, 90005301, 90005860, 90005861, 90005880, 90005792}


def map_tier(map_id: str) -> int:
    aa = int(map_id[1:3])
    return int(map_id[10:12]) if aa in (60, 61) else 0


def map_xyz_to_marker(map_id, x, y, z, conv):
    aa, bb, cc = int(map_id[1:3]), int(map_id[4:6]), int(map_id[7:9])
    return place(aa, bb, cc, x, y, z, conv, tier=map_tier(map_id))


def load_item_names(dvd, mod, helper):
    out = {}
    for loc, folder in LOCALES.items():
        tables = {}
        for fn in ("item.msgbnd.dcx", "item_dlc02.msgbnd.dcx"):
            p = f"/msg/{folder}/{fn}"
            if not modfiles.has(dvd, mod, p):
                continue
            for k, v in fmg.load_msgbnd(modfiles.read(dvd, mod, p), oodle=helper).items():
                tables.setdefault(k.split("_dlc")[0], {}).update(v)
        out[loc] = tables
    return out


def item_name(names_by_loc, loc, item_id, category):
    table = CATEGORY_TABLES.get(category)
    if not table:
        return ""
    en = names_by_loc["en"]
    text = names_by_loc.get(loc, {}).get(table, {}).get(item_id, "")
    if not text or text.startswith("%null%"):
        text = en.get(table, {}).get(item_id, "")
    return "" if not text or text.startswith("%null%") else text




def lot_is_guaranteed(lot_row, lot_def):
    """True when no weighted empty slot can win this ItemLot draw.

    This is the same discriminator used by Map-for-Goblins for guaranteed
    enemy drops: a random/farmable lot normally has a weighted "nothing"
    slot, while one-time equipment/reward sub-lots do not.
    """
    for slot in range(1, 9):
        iid = lot_def.get(lot_row.data, f"lotItemId{slot:02d}") or 0
        bp = lot_def.get(lot_row.data, f"lotItemBasePoint{slot:02d}") or 0
        if iid == 0 and bp > 0:
            return False
    return True


def iter_flagged_unique_lots(base_lot_id, lot_source, map_lots, enemy_lots, lot_def):
    """Yield (lot_id,row,flag) for persistent guaranteed lots of one NPC.

    Enemy ItemLots commonly form a contiguous base+N chain.  The base row can
    have no pickup flag while a later row contains the actual one-time item, so
    checking only the base row misses unique equipment/set drops.
    """
    if lot_source == "enemy" and base_lot_id in enemy_lots:
        for off in range(1000):
            lid = base_lot_id + off
            row = enemy_lots.get(lid)
            if row is None:
                break
            flag = lot_def.get(row.data, "getItemFlagId") or 0
            if flag and lot_is_guaranteed(row, lot_def):
                yield lid, row, flag
        return

    row = map_lots.get(base_lot_id) or enemy_lots.get(base_lot_id)
    if row is None:
        return
    flag = lot_def.get(row.data, "getItemFlagId") or 0
    if flag and lot_is_guaranteed(row, lot_def):
        yield base_lot_id, row, flag

def direct_drop_allowed(team_type: int, marker_category: str) -> bool:
    """Whether a raw NpcParam death-lot is a collection-worthy combat drop.

    Merchant Bell Bearings are the sole friendly-NPC exception.  They are kept
    because killing roaming merchants is a common full-collection workflow and
    the project already gives them a dedicated category/icon.
    """
    return marker_category == "merchant_bell_bearings" or team_type in DIRECT_HOSTILE_TEAMS


def headline(lot_row, lot_def, names_by_loc):
    """First named, non-empty item slot -> (itemId, category, names) or None."""
    for slot in range(1, 9):
        iid = lot_def.get(lot_row.data, f"lotItemId{slot:02d}")
        cat = lot_def.get(lot_row.data, f"lotItemCategory{slot:02d}")
        if not iid or not cat:
            continue
        en_name = item_name(names_by_loc, "en", iid, cat)
        if not en_name:
            continue
        names = {loc: (item_name(names_by_loc, loc, iid, cat) or en_name) for loc in LOCALES}
        return iid, cat, en_name, names
    return None


def headline_for_mfg_category(lot_row, lot_def, names_by_loc, wanted):
    """First lot item classified as ``wanted``; used for explicit exceptions.

    A death lot may contain more than one item.  For the roaming-merchant
    exception we must not assume the Bell Bearing happens to be slot 1.
    """
    for slot in range(1, 9):
        iid = lot_def.get(lot_row.data, f"lotItemId{slot:02d}")
        cat = lot_def.get(lot_row.data, f"lotItemCategory{slot:02d}")
        if not iid or not cat:
            continue
        en_name = item_name(names_by_loc, "en", iid, cat)
        if not en_name:
            continue
        if mfg_categories.categorise(iid, en_name, cat) != wanted:
            continue
        names = {loc: (item_name(names_by_loc, loc, iid, cat) or en_name) for loc in LOCALES}
        return iid, cat, en_name, names
    return None


def enemy_parts(m):
    """Yield live MSB Enemy placements with minimal string decoding.

    The old implementation called ``m.entries`` for the entire MODEL and PARTS
    lists. That eagerly decoded every UTF-16 part/model name although part names
    are never used by this extractor. Across the complete Elden Ring map corpus
    that is a substantial amount of Python-level byte scanning. Here we walk raw
    entry offsets and decode only model names actually referenced by Enemy parts.
    """
    model_list = m.lists.get("MODEL_PARAM_ST")
    parts_list = m.lists.get("PARTS_PARAM_ST")
    model_offsets = model_list.entry_offsets if model_list else []
    part_offsets = parts_list.entry_offsets if parts_list else []
    model_names = {}

    def model_name(index):
        if not (0 <= index < len(model_offsets)):
            return ""
        cached = model_names.get(index)
        if cached is not None:
            return cached
        off = model_offsets[index]
        try:
            value = m.entry_name(off)
        except (IndexError, struct.error):
            value = ""
        model_names[index] = value
        return value

    for off in part_offsets:
        if off <= 0 or off >= len(m.data):
            continue
        try:
            if m.u32(off + PART_TYPE) != PART_TYPE_ENEMY:
                continue
            if m.i32(off + PART_GAME_EDITION_DISABLE) == 1:
                continue
            entity_rel = m.i64(off + PART_ENTITY_DATA_PTR)
            type_rel = m.i64(off + PART_TYPE_DATA_PTR)
            if entity_rel <= 0 or type_rel <= 0:
                continue
            entity = m.u32(off + entity_rel + ENTITY_ID)
            npc = m.i32(off + type_rel + ENEMY_NPC_PARAM_ID)
            model_i = m.i32(off + PART_MODEL_INDEX)
            x, y, z = m.vec3(off + PART_POSITION)
        except (IndexError, struct.error):
            continue
        yield {
            "entity": entity, "npc": npc, "model": model_name(model_i),
            "x": x, "y": y, "z": z,
        }


def choose_exact_placement(placements, emevd_map):
    """Prefer the entity placement in the EMEVD's own map/tile."""
    exact = [p for p in placements if p["map"] == emevd_map]
    if exact:
        return min(exact, key=lambda p: p["tier"])
    # Some aggregate/tier names differ only in the trailing two digits.  Stay
    # within the same area/grid before falling back globally.
    prefix = emevd_map[:10]
    same = [p for p in placements if p["map"][:10] == prefix]
    if same:
        return min(same, key=lambda p: p["tier"])
    return min(placements, key=lambda p: p["tier"]) if placements else None




def infer_entity_from_call(arg_data, emevd_map, entities):
    """Return (entity_id, placement) by matching literal call args to MSB IDs."""
    candidates = []
    seen = set()
    # bytes 0..7 are slot + called event id, never an EntityID parameter.
    for off in range(8, len(arg_data) - 3, 4):
        value = struct.unpack_from("<I", arg_data, off)[0]
        if value in seen or value not in entities:
            continue
        seen.add(value)
        placement = choose_exact_placement(entities[value], emevd_map)
        if placement is None:
            continue
        # Prefer the caller's exact map, then its area/grid prefix.  This is
        # important because a few EntityIDs are reused in never-co-loaded maps.
        rank = 2
        if placement["map"] == emevd_map:
            rank = 0
        elif placement["map"][:10] == emevd_map[:10]:
            rank = 1
        candidates.append((rank, off, value, placement))
    if not candidates:
        return None, None
    candidates.sort(key=lambda x: (x[0], x[1]))
    _, _, entity_id, placement = candidates[0]
    return entity_id, placement

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--game-dir", default=None)
    ap.add_argument("--mod-dir", default=None)
    ap.add_argument("--limit", type=int, default=0, help="only N maps (for testing)")
    args = ap.parse_args()

    game = require_game_dir(args.game_dir)
    mod = modfiles.find_mod_dir(args.mod_dir)
    status = mfg_categories.data_status()
    if status:
        print(status)
    t0 = time.time()
    dvd = DvdBnd(game, cache_dir=os.path.join(ROOT, "cache"), verbose=False)
    helper = oodle.make_helper(game)

    print("loading params ...")
    params = param.load_params(modfiles.regulation_path(game, mod))
    lot_def = paramdef.load(os.path.join(DEFS, "ItemLotParam.xml"))
    conv = LegacyConv(params["WorldMapLegacyConvParam"].rows,
                      paramdef.load(os.path.join(DEFS, "WorldMapLegacyConvParam.xml")))
    map_lots = {r.id: r for r in params["ItemLotParam_map"].rows}
    enemy_lots = {r.id: r for r in params["ItemLotParam_enemy"].rows}
    all_lots = dict(enemy_lots)
    all_lots.update(map_lots)  # map-lot id wins on a collision, matching game use here
    npc_param = params.get("NpcParam")
    if npc_param is None:
        sys.exit("NpcParam missing from regulation.bin")
    if npc_param.row_size <= NPC_TEAM_TYPE:
        sys.exit(f"NpcParam row layout too small ({npc_param.row_size} bytes); offsets need updating")
    npc_lots = {}
    for r in npc_param.rows:
        enemy = struct.unpack_from("<i", r.data, NPC_ITEM_LOT_ENEMY)[0]
        map_lot = struct.unpack_from("<i", r.data, NPC_ITEM_LOT_MAP)[0]
        team_type = r.data[NPC_TEAM_TYPE]
        npc_lots[r.id] = (map_lot, enemy, team_type)
    print(f"  map lots={len(map_lots):,}, enemy lots={len(enemy_lots):,}, NPCs={len(npc_lots):,}")

    # NPC definitions repeat across many placements. Resolve each NPC's
    # one-time ItemLot chain once instead of walking base+N and inspecting up
    # to eight slots again for every Enemy instance in every MSB.
    npc_drop_cache = {}
    lot_chain_cache = {}

    def unique_lot_chain(base_lot, lot_source):
        key = (int(base_lot), lot_source)
        cached = lot_chain_cache.get(key)
        if cached is None:
            cached = tuple(
                (lot_id, pickup_flag)
                for lot_id, _row, pickup_flag in iter_flagged_unique_lots(
                    base_lot, lot_source, map_lots, enemy_lots, lot_def
                )
            )
            lot_chain_cache[key] = cached
        return cached

    def npc_drop_spec(npc_id):
        if npc_id in npc_drop_cache:
            return npc_drop_cache[npc_id]
        lots = npc_lots.get(npc_id)
        if not lots:
            result = ()
        else:
            map_lot, enemy_lot, team_type = lots
            if map_lot > 0:
                base_lot, lot_source = map_lot, "map"
            elif enemy_lot > 0:
                base_lot, lot_source = enemy_lot, "enemy"
            else:
                result = ()
                npc_drop_cache[npc_id] = result
                return result
            result = tuple(
                (lot_id, pickup_flag, lot_source, team_type)
                for lot_id, pickup_flag in unique_lot_chain(base_lot, lot_source)
            )
        npc_drop_cache[npc_id] = result
        return result

    print("loading item names ...")
    names_by_loc = load_item_names(dvd, mod, helper)

    map_list = os.path.join(ROOT, "cache", "map-list.txt")
    if not os.path.exists(map_list):
        sys.exit("run tools/enumerate_maps.py first (creates cache/map-list.txt)")
    map_ids = [line.split("\t")[0] for line in open(map_list, encoding="utf-8") if line.strip()]
    if args.limit:
        map_ids = map_ids[:args.limit]

    print(f"\nindexing Enemy parts in {len(map_ids)} MSBs ...")
    phase_started = time.monotonic()
    last_report = phase_started
    entities = defaultdict(list)  # EntityID -> placement records
    direct_candidates = []
    stats = Counter()
    enemy_count = 0
    for i, map_id in enumerate(map_ids):
        path = f"/map/mapstudio/{map_id}.msb.dcx"
        if not modfiles.has(dvd, mod, path):
            continue
        try:
            m = msblib.load(dcx.decompress(modfiles.read(dvd, mod, path), oodle=helper))
        except Exception:
            stats["msb parse failed"] += 1
            continue
        tier = map_tier(map_id)
        for e in enemy_parts(m):
            if e["entity"] > 0:
                rec = {**e, "map": map_id, "tier": tier}
                entities[e["entity"]].append(rec)
            enemy_count += 1
            if e["entity"] <= 0:
                continue
            # Cached by NPC id: repeated mobs now pay only a dictionary lookup.
            for lot_id, pickup_flag, lot_source, team_type in npc_drop_spec(e["npc"]):
                direct_candidates.append({**e, "map": map_id, "tier": tier,
                                          "lot": lot_id, "flag": pickup_flag,
                                          "lot_source": lot_source,
                                          "team_type": team_type,
                                          "source": "npc_unique"})
        now = time.monotonic()
        if (i + 1) == len(map_ids) or (i + 1) % 25 == 0 or now - last_report >= 5.0:
            print(f"  MSB {i + 1}/{len(map_ids)} | enemies={enemy_count:,} | "
                  f"entity IDs={len(entities):,} | candidates={len(direct_candidates):,} | "
                  f"{now - phase_started:.1f}s")
            last_report = now

    # Deduplicate LOD copies of a direct NPC->lot placement.  Entity IDs can be
    # reused in unrelated legacy maps, so the area/grid prefix remains in key.
    direct_best = {}
    for r in direct_candidates:
        key = (r["map"][:10], r["entity"], r["lot"])
        old = direct_best.get(key)
        if old is None or r["tier"] < old["tier"]:
            direct_best[key] = r
    print(f"  {len(direct_best):,} direct one-time NPC lots; "
          f"NPC specs cached={len(npc_drop_cache):,}; lot chains cached={len(lot_chain_cache):,}; "
          f"MSB phase={time.monotonic() - phase_started:.1f}s")

    print("\nscanning EMEVD one-time reward templates ...")
    scripted = []
    event_names = {"common", "common_func"}
    for mid in map_ids:
        # Overworld LOD variants share the tier-0 event script.
        if int(mid[1:3]) in (60, 61):
            event_names.add(mid[:10] + "00")
        else:
            event_names.add(mid)
    event_read = 0
    event_bad = 0
    event_list = sorted(event_names)
    event_started = time.monotonic()
    last_report = event_started
    for event_i, emap in enumerate(event_list, 1):
        ep = f"/event/{emap}.emevd.dcx"
        if not modfiles.has(dvd, mod, ep):
            continue
        try:
            raw = dcx.decompress(modfiles.read(dvd, mod, ep), oodle=helper)
            instructions = emevd.iter_instructions(raw)
            event_read += 1
            for inst in instructions:
                if inst.bank != 2000 or inst.id not in (0, 6) or len(inst.args) < 8:
                    continue
                event_id = struct.unpack_from("<i", inst.args, 4)[0]
                spec = TEMPLATE_EVENTS.get(event_id)
                if spec is None:
                    continue
                lot_off, need = spec
                if len(inst.args) < need:
                    continue
                lot_id = struct.unpack_from("<i", inst.args, lot_off)[0]
                if lot_id <= 0 or lot_id not in all_lots:
                    continue
                entity_id, placement = infer_entity_from_call(inst.args, emap, entities)
                if entity_id is None or placement is None:
                    continue
                lot_row = all_lots[lot_id]
                lot_flag = lot_def.get(lot_row.data, "getItemFlagId") or 0
                kill_flag = (struct.unpack_from("<i", inst.args, 8)[0]
                             if event_id in CALLER_KILL_FLAG_EVENTS and len(inst.args) >= 12 else 0)
                scripted.append({**placement, "lot": lot_id,
                                 "flag": kill_flag or lot_flag or None,
                                 "event": event_id, "source": "emevd"})
        except Exception as exc:
            event_bad += 1
            if event_bad <= 3:
                print(f"  ! {emap}: {exc}")
        now = time.monotonic()
        if event_i == len(event_list) or event_i % 25 == 0 or now - last_report >= 5.0:
            print(f"  EMEVD {event_i}/{len(event_list)} | read={event_read} | "
                  f"matches={len(scripted):,} | bad={event_bad} | {now - event_started:.1f}s")
            last_report = now
    print(f"  {event_read} event files read; {len(scripted):,} matched calls; {event_bad} parse failures; "
          f"EMEVD phase={time.monotonic() - event_started:.1f}s")

    # Scripted placement is more authoritative than NpcParam for the same
    # entity+lot.  Keep it first and suppress a direct duplicate.
    scripted_keys = {(r["entity"], r["lot"]) for r in scripted}
    rows = scripted + [r for r in direct_best.values()
                       if (r["entity"], r["lot"]) not in scripted_keys]

    # Collapse exact duplicate event calls/LOD records.
    unique = {}
    for r in rows:
        key = (r["entity"], r["lot"], r["map"][:10])
        old = unique.get(key)
        if old is None or (r["source"] == "emevd" and old["source"] != "emevd"):
            unique[key] = r

    markers = []
    dropped = Counter()
    cat_counts = Counter()
    source_counts = Counter()
    for r in sorted(unique.values(), key=lambda x: (x["map"], x["entity"], x["lot"])):
        lot_row = all_lots.get(r["lot"])
        merchant_head = None
        if r["source"] == "npc_unique" and lot_row is not None:
            merchant_head = headline_for_mfg_category(
                lot_row, lot_def, names_by_loc, "merchant_bell_bearings")
        # If this is a roaming-merchant death lot, use the Bell Bearing itself
        # as the marker headline/icon even when another drop occupies an
        # earlier slot.  This keeps the friendly-NPC exception narrow and
        # visually explicit.
        head = merchant_head or (headline(lot_row, lot_def, names_by_loc) if lot_row else None)
        if head is None:
            dropped["no resolvable headline item"] += 1
            continue
        iid, item_cat, en_name, loc_names = head
        p = map_xyz_to_marker(r["map"], r["x"], r["y"], r["z"], conv)
        if p is None:
            dropped["unplaceable"] += 1
            continue
        mcat = mfg_categories.categorise(iid, en_name, item_cat)

        # Raw NpcParam death lots also exist on friendly quest NPCs.  Do not
        # turn "you can murder this NPC" into a full-collection requirement.
        # Scripted EMEVD combat rewards remain authoritative and bypass this
        # base-team check; this also means an NPC who later invades is shown at
        # the invasion reward, not at their normal friendly placement/death lot.
        if r["source"] == "npc_unique":
            team_type = r.get("team_type", -1)
            if not direct_drop_allowed(team_type, mcat):
                if team_type in FRIENDLY_TEAM_TYPES:
                    dropped["friendly/neutral NPC death lot"] += 1
                else:
                    dropped[f"non-hostile/unknown teamType {team_type}"] += 1
                continue

        lot_items = []
        seen_lot_items = set()
        if lot_row is not None:
            for slot in range(1, 9):
                liid = lot_def.get(lot_row.data, f"lotItemId{slot:02d}") or 0
                lcat = lot_def.get(lot_row.data, f"lotItemCategory{slot:02d}") or 0
                if liid and lcat and (int(lcat), int(liid)) not in seen_lot_items:
                    seen_lot_items.add((int(lcat), int(liid)))
                    lot_items.append({"itemId": int(liid), "itemCategory": int(lcat)})

        marker = {
            "id": f"drop:{r['map']}:{r['entity']}:{r['lot']}",
            "cat": mcat,
            "names": loc_names,
            "flag": r.get("flag"),
            "master": p[2], "px": round(p[0], 1), "py": round(p[1], 1), "h": round(p[3]),
            "map": r["map"], "entity": r["entity"], "npc": r.get("npc", 0),
            "model": r.get("model", ""), "lot": r["lot"],
            "itemId": iid, "itemCategory": item_cat, "lotItems": lot_items,
            "source": r["source"], "icon": mfg_categories.icon_for(mcat),
        }
        if r.get("event"):
            marker["event"] = r["event"]
        if r["source"] == "npc_unique" and mcat == "merchant_bell_bearings":
            marker["special"] = "merchant_kill"
        markers.append(marker)
        cat_counts[mcat] += 1
        source_counts[r["source"]] += 1

    out = os.path.join(ROOT, "data", "unique_drops.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump({"locales": list(LOCALES), "markers": markers}, f, ensure_ascii=False)

    print(f"\nunique-drop markers: {len(markers):,}")
    print("  by source: " + ", ".join(f"{k}={v}" for k, v in source_counts.most_common()))
    print("  by category: " + ", ".join(f"{k}={v}" for k, v in cat_counts.most_common()))
    if dropped:
        print("  dropped: " + ", ".join(f"{k}={v}" for k, v in dropped.most_common()))
    no_flag = sum(1 for m in markers if not m.get("flag"))
    print(f"  automatic completion flags: {len(markers)-no_flag:,}; manual-only: {no_flag:,}")
    print(f"-> {out} ({os.path.getsize(out):,} bytes)   {time.time()-t0:.0f}s")
    dvd.close()


if __name__ == "__main__":
    main()
