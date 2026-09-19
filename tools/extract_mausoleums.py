"""Extract Walking Mausoleums from MSB Enemy placements.

Walking Mausoleums are c4450 Enemy parts, so their coordinates come directly
from the same game MSBs used by the rest of this project.  They receive their
own ``mausoleum`` category and use the game's existing mausoleum-shaped world
map sprite (iconId 45 / MENU_MAP_45) rather than a generic enemy/item icon.

The game's "lowered" state and the altar's one-use remembrance-duplication state
are not the same thing.  This extractor therefore leaves ``flag`` empty instead
of pretending one of those states means full completion; the existing map UI
then gives the marker a manual checkbox.  Position/category/icon are automatic.

    python tools/extract_mausoleums.py -> data/mausoleums.json
"""
from __future__ import annotations

import argparse
import json
import os
import struct
import sys
import time

reconfigure = getattr(sys.stdout, "reconfigure", None)
if reconfigure:
    reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from erlib import dcx, msb as msblib, oodle, param, paramdef
import erlib.modfiles as modfiles
from erlib.dvdbnd import DvdBnd
from erlib.gamepath import require_game_dir
from build_markers import LegacyConv, LOCALES, place

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFS = os.path.join(ROOT, "data", "paramdefs")

PART_TYPE = 0x0C
PART_MODEL_INDEX = 0x14
PART_POSITION = 0x20
PART_GAME_EDITION_DISABLE = 0x44
PART_ENTITY_DATA_PTR = 0x60
PART_TYPE_ENEMY = 2
ENTITY_ID = 0x00
MODEL = "c4450"

# Existing in-game world-map sprite used by "Mohgwyn Dynasty Mausoleum".
# extract_icons.py already extracts it from the user's own game assets because
# WorldMapPointParam references the same icon id.
MAUSOLEUM_ICON = 45

NAMES = {
    "en": "Walking Mausoleum",
    "ru": "Блуждающий мавзолей",
    "zh": "漫步灵庙",
}


def map_tier(map_id):
    aa = int(map_id[1:3])
    return int(map_id[10:12]) if aa in (60, 61) else 0


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--game-dir", default=None)
    ap.add_argument("--mod-dir", default=None)
    args = ap.parse_args()

    game = require_game_dir(args.game_dir)
    mod = modfiles.find_mod_dir(args.mod_dir)
    t0 = time.time()
    dvd = DvdBnd(game, cache_dir=os.path.join(ROOT, "cache"), verbose=False)
    helper = oodle.make_helper(game)
    params = param.load_params(modfiles.regulation_path(game, mod))
    conv = LegacyConv(params["WorldMapLegacyConvParam"].rows,
                      paramdef.load(os.path.join(DEFS, "WorldMapLegacyConvParam.xml")))

    map_list = os.path.join(ROOT, "cache", "map-list.txt")
    if not os.path.exists(map_list):
        sys.exit("run tools/enumerate_maps.py first (creates cache/map-list.txt)")
    map_ids = [line.split("\t")[0] for line in open(map_list, encoding="utf-8") if line.strip()]

    candidates = []
    for map_id in map_ids:
        path = f"/map/mapstudio/{map_id}.msb.dcx"
        if not modfiles.has(dvd, mod, path):
            continue
        try:
            m = msblib.load(dcx.decompress(modfiles.read(dvd, mod, path), oodle=helper))
        except Exception:
            continue
        models = m.entries("MODEL_PARAM_ST")
        for off, part_name in m.entries("PARTS_PARAM_ST"):
            try:
                if m.u32(off + PART_TYPE) != PART_TYPE_ENEMY:
                    continue
                if m.i32(off + PART_GAME_EDITION_DISABLE) == 1:
                    continue
                model_i = m.i32(off + PART_MODEL_INDEX)
                model = models[model_i][1] if 0 <= model_i < len(models) else ""
                if model != MODEL:
                    continue
                rel = m.i64(off + PART_ENTITY_DATA_PTR)
                if rel <= 0:
                    continue
                entity = m.u32(off + rel + ENTITY_ID)
                x, y, z = m.vec3(off + PART_POSITION)
            except (IndexError, struct.error):
                continue
            candidates.append({"map": map_id, "tier": map_tier(map_id), "entity": entity,
                               "part": part_name, "x": x, "y": y, "z": z})

    # c4450 may be present in coarse LOD copies; keep the detailed placement.
    best = {}
    for r in candidates:
        # Entity IDs are normally stable, but do not assume global uniqueness
        # across unrelated maps.  Ignore only the final map tier (dd) so LOD
        # copies of the same placement still collapse to one record.
        map_group = r["map"][:9]  # e.g. m60_36_44 from m60_36_44_00
        key = ("entity", map_group, r["entity"]) if r["entity"] else ("part", map_group, r["part"])
        old = best.get(key)
        if old is None or r["tier"] < old["tier"]:
            best[key] = r

    markers = []
    for n, r in enumerate(sorted(best.values(), key=lambda x: (x["map"], x["entity"]))):
        aa, bb, cc = int(r["map"][1:3]), int(r["map"][4:6]), int(r["map"][7:9])
        p = place(aa, bb, cc, r["x"], r["y"], r["z"], conv, tier=r["tier"])
        if p is None:
            continue
        names = {loc: NAMES.get(loc, NAMES["en"]) for loc in LOCALES}
        markers.append({
            "id": f"mausoleum:{r['map'][:9]}:{r['entity'] or n}",
            "cat": "mausoleum",
            "names": names,
            "flag": None,
            "master": p[2], "px": round(p[0], 1), "py": round(p[1], 1), "h": round(p[3]),
            "map": r["map"], "entity": r["entity"], "model": MODEL,
            "source": "msb_enemy", "icon": MAUSOLEUM_ICON,
        })

    out = os.path.join(ROOT, "data", "mausoleums.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump({"locales": list(LOCALES), "markers": markers}, f, ensure_ascii=False)
    print(f"Walking Mausoleums: {len(markers)} -> {out} ({time.time()-t0:.0f}s)")
    if markers:
        for m in markers:
            print(f"  {m['map']} entity={m['entity']} ({m['px']:.1f},{m['py']:.1f})")
    dvd.close()


if __name__ == "__main__":
    main()
