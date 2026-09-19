from __future__ import annotations

TILE_WORLD = 256
OFFSET_X = -7168
OFFSET_Y = 16640


def _anchor_rank(r):
    dst = r.get("dst", [0, 0, 0])
    sp = r.get("srcPos", [0, 0, 0]); dp = r.get("dstPos", [0, 0, 0])
    return (0 if dst[0] in (60, 61) else 1, 0 if r.get("base") else 1,
            0 if (sp[0] or sp[2]) else 1, 0 if (dp[0] or dp[2]) else 1)


class Projector:
    def __init__(self, doc):
        self.by_block = {}
        for r in (doc or {}).get("rows", []):
            self.by_block.setdefault(tuple(r["src"]), []).append(r)
        for rows in self.by_block.values():
            rows.sort(key=_anchor_rank)
        self.underground = {tuple(x) for x in (doc or {}).get("undergroundBlocks", [])}

    def _rows(self, area, block, mapno):
        return self.by_block.get((area, block, mapno)) or self.by_block.get((area, block, 0))

    def _resolve(self, area, block, mapno, x, y, z, depth=0):
        if area in (60, 61):
            return {"px": block*TILE_WORLD + TILE_WORLD/2 + x + OFFSET_X,
                    "py": OFFSET_Y - (mapno*TILE_WORLD + TILE_WORLD/2 + z),
                    "h": y, "area": area}
        if depth > 4: return None
        rows = self._rows(area, block, mapno)
        if not rows: return None
        b = rows[0]; sp=b["srcPos"]; dp=b["dstPos"]; d=b["dst"]
        return self._resolve(d[0], d[1], d[2], x-sp[0]+dp[0], y-sp[1]+dp[1], z-sp[2]+dp[2], depth+1)

    def project(self, position):
        if not position: return None
        b = position.get("mapBytes") or position.get("map_id_bytes")
        if not b or len(b) != 4: return None
        area, block, mapno = b[3], b[2], b[1]
        r = self._resolve(area, block, mapno, position["x"], position["y"], position["z"])
        if not r: return None
        master = "M10" if r["area"] == 61 else ("M01" if (area, block) in self.underground else "M00")
        return {"px": round(r["px"],1), "py": round(r["py"],1), "h": round(r["h"]), "master": master}
