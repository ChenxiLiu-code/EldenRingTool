from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path


@lru_cache(maxsize=1)
def content_overrides():
    path = Path(__file__).resolve().parents[2] / "data" / "content-pack-overrides.json"
    return json.loads(path.read_text(encoding="utf-8"))


def content_pack(row):
    pack = row.get("contentPack", "")
    if pack.startswith("模组新增："):
        return pack
    key = row.get("key") or f"{row.get('type')}:{row.get('id')}"
    return content_overrides().get("items", {}).get(key, content_overrides().get("legacyLabels", {}).get(pack, pack))


def collection_category(row):
    if row.get("type") == "goods" and str(row.get("id")) in {"2009600", "2009610", "2009620"}:
        return "steed_appearances"
    # Older generated catalogs classified the Whetstone Knife as progression.
    # Correct it on read as well, without invalidating the resource cache.
    if row.get("type") == "goods" and str(row.get("id")) == "8590":
        return "whetblades"
    if row.get("type") == "goods" and row.get("category") == "misc":
        from tools.erlib.mfg_categories import categorise
        cat = categorise(int(row["id"]), (row.get("names") or {}).get("en", ""), 1)
        if cat in COLLECTION_CATEGORIES:
            return cat
    return str(row.get("category") or row.get("type") or "item")


def is_collectible(row):
    if any("dlc dummy" in str(name).lower() for name in (row.get("names") or {}).values()):
        return False
    cat = collection_category(row)
    if cat != row.get("category") and cat in COLLECTION_CATEGORIES:
        return True
    return row.get("collectible", cat in COLLECTION_CATEGORIES or cat in {"gesture", "gestures"})

def build_index(doc):
    doc = doc if isinstance(doc,dict) else {"schema":2,"items":[],"categories":{}}
    # Upgrade old in-memory catalogs without rewriting fingerprinted files.
    rows = {}
    goods_ids = {int(r["id"]) for r in doc.get("items", []) if r.get("type") == "goods"}
    for original in doc.get("items", []):
        if collection_category(original) == str(original.get("category") or original.get("type") or "item"):
            key = original.get("key") or f"{original.get('type')}:{original.get('id')}"
            rows[key] = original
            continue
        row = dict(original)
        row["collectible"] = is_collectible(original)
        row["category"] = collection_category(original)
        ident = int(row.get("id", 0))
        aliases = set(row.get("aliases") or [ident])
        if row.get("type") == "goods" and row["category"] == "spirits":
            base = ident - ident % 100
            if ident % 100 <= 10 and base in goods_ids:
                ident = base
        key = f"{row.get('type')}:{ident}"
        previous = rows.get(key)
        if previous:
            aliases.update(previous.get("aliases", []))
            sources = previous.get("sources", []) + [src for src in row.get("sources", []) if src not in previous.get("sources", [])]
            if int(original.get("id", 0)) != ident:
                row = dict(previous)
            row["sources"] = sources
            row["acquisitionFlags"] = sorted(set(previous.get("acquisitionFlags", [])) | set(original.get("acquisitionFlags", [])))
        row.update(id=ident, key=key, aliases=sorted(aliases))
        rows[key] = row
    doc["items"] = list(rows.values())
    by_id={}; by_alias={}
    for row in doc.get("items",[]):
        i=int(row.get("id",0)) & 0xffffffff; by_id[f"{row.get('type')}:{i}"]=row
        aliases=row.get("aliases") if isinstance(row.get("aliases"),list) else [row.get("id")]
        for a in aliases:
            sig=f"{row.get('type')}:{int(a)&0xffffffff}"; by_alias.setdefault(sig,row)
    return {"doc":doc,"by_id":by_id,"by_alias":by_alias}

def lookup(index, typ, ident):
    ident=int(ident)&0xffffffff; row=index["by_alias"].get(f"{typ}:{ident}") or index["by_id"].get(f"{typ}:{ident}")
    if row or typ != "weapon": return row
    level=ident%100
    if level<=25:
        affinity=ident-level; row=index["by_alias"].get(f"weapon:{affinity}") or index["by_id"].get(f"weapon:{affinity}")
        if row:return row
        base=affinity-(affinity%10000); return index["by_id"].get(f"weapon:{base}")
    return None

def resolve(index, raw, gesture_ids=()):
    owned={}; unresolved=0
    for it in (raw or {}).get("items",[]):
        row=lookup(index,it.get("type"),it.get("id"))
        if not row: unresolved+=1; continue
        key=row.get("key") or f"{row.get('type')}:{row.get('id')}"; x=owned.setdefault(key,{"quantity":0,"held":0,"storage":0})
        for k in ("quantity","held","storage"): x[k]+=int(it.get(k,0) or 0)
    for gid in gesture_ids:
        row=index["by_id"].get(f"gesture:{int(gid)&0xffffffff}")
        if row: owned[row.get("key") or f"gesture:{int(gid)&0xffffffff}"]={"quantity":1,"held":1,"storage":0}
    return {"owned":owned,"unresolved":unresolved+int((raw or {}).get("unknownHandles",0) or 0),"distinct":len(owned),
            "quantity":sum(x["quantity"] for x in owned.values()),"heldEntries":(raw or {}).get("held"),"storageEntries":(raw or {}).get("storage")}


COLLECTION_CATEGORIES = {
    # Permanent/non-consumed collection identities.  Consumable progression
    # items (Larval Tears, Stonesword Keys, Deathroot, Bell Bearings after
    # turning them in, etc.) remain browsable under “all items”, but are not
    # counted in the default completion percentage because current inventory
    # cannot prove they were never acquired and subsequently spent/handed in.
    "armaments", "armour", "talismans", "ashes_of_war", "spirits",
    "crystal_tears", "incantations", "sorceries", "reusables",
    "prattling_pates", "cookbooks", "whetblades", "memory_stones",
    "pots_n_perfumes", "great_runes", "world_maps", "steed_appearances",
    # ERR/Reforged-specific permanent collections, when those rows exist.
    "fortunes", "sealed_curios",
}
