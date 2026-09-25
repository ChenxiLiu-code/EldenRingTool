"""Apply conservative Chinese copy edits to the local route-note cache.

The English source and credits stay in tips.json. Entries marked reviewed are
left alone so a later machine-translation pass cannot replace manual edits.
"""
from __future__ import annotations

import json
import re
from hashlib import sha256
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / "data" / "tips-zh.json"
TIPS_PATH = ROOT / "data" / "tips.json"

ROUTES = {
    "item:1051360110": "强化素材。位于城堡北部，被椅子围绕的大型纪念碑旁的尸体上。",
    "poi:65485700": "进入化圣雪原后前往封印监牢；与监牢交互后才能取得其中的物品。",
    "grace:62374600": "结缘教堂赐福，位于教堂正门内侧。",
    "item:1049390010": "位于魔法镇瑟利亚较低处的建筑屋顶；从相邻屋顶跳过去取得。",
    "item:1034471060": "湖之利耶尼亚西部的石棺中共有5个。",
    "item:1036440100": "关键道具。学院门前镇一座破损建筑的屋顶塔楼内，打开宝箱取得。",
    "item:14000770": "位于魔法学院雷亚卢卡利亚的杜鹃教堂二楼西侧尸体上。从屋顶穿过教堂破损的玻璃窗才能到达。",
    "item:1051360070": "关键道具。位于红狮子城正门东侧门楼的底层。",
    "item:13000030": "消耗品。位于右侧墙洞前的尸体上，附近有兽人守卫。",
    "item:14000840": "位于魔法学院雷亚卢卡利亚的杜鹃教堂二楼东侧，在布满结晶的房间地面上。",
    "poi:63365200": "火山南侧的一间小屋。",
    "item:1035500040": "制作笔记。位于花园东南侧小房间内的尸体上。",
    "item:1040390000": "位于坍塌桥梁边缘一具坐着的尸体上。",
    "item:1035500300": "圣杯瓶强化素材。位于城寨上层的幻影树下。",
    "poi:61453700": "通往希芙拉河南部地下区域的井口。",
    "item:1052410030": "卢恩消耗品。位于悬崖高处的一组石棺中；可借助雷恩魔法师塔附近的灵魂气流抵达。",
    "item:14000660": "消耗品，共5个。遭遇三名人偶兵和一名魔法师后，在塔上的尸体处拾取。",
    "item:1035500200": "小盾。位于花园内尖石柱旁高处的尸体上；可从附近泪滴粪金龟的位置跳上岩石。",
    "item:13000035": "骨灰强化素材。位于“渐毁野兽墓（深处）”旁大建筑上层东北角的墙龛。先从赐福旁房间的阳台跳到红色屋顶，再由屋顶进入上层。",
    "item:10000470": "石剑钥匙。位于城墙塔顶端可抵达的一处破顶建筑内，拾取尸体上的道具；途中需要小心跳过平台。",
    "item:16000520": "骨灰。位于火山官邸牢镇内一处由敌人把守的祭坛上。",
    "grace:160003": "位于火山官邸牢镇教堂内的赐福。",
    "item:16000290": "强化素材。搭乘火山官邸牢镇的笼式升降梯上去后右转，在悬崖边悬挂的尸体上拾取。",
    "item:16000280": "强化素材。位于火山官邸与熔岩土龙交战的洞窟深处，拾取尸体上的道具。",
    "item:16000090": "从火山官邸大厅进入走廊后上楼，进入右侧第一间房。穿过蜗牛出没的房间，在岔路先走左侧门洞；沿路到尽头拾取“流浪战士的制作笔记【21】”。再寻找左侧的隐藏墙，进入有“堕落调香师”卡尔曼骨灰的房间。",
    "boss:16000850": "从火山官邸“迎宾厅”赐福向东越过熔岩，经屋顶抵达笼式升降梯。上楼后启动机关，放下通往“牢镇教堂”的吊桥；继续上楼进入教堂，与神皮贵族交战。",
    "grace:160002": "位于火山官邸入口内的赐福。",
    "grace:160001": "击败火山官邸的神皮贵族后出现的赐福。",
    "grace:160006": "位于火山官邸地下洞窟，击败掳人少女人偶后可抵达。",
    "item:16000130": "圣印记。位于火山官邸牢镇靠近恶兆猎人的建筑内，从尸体上拾取。",
    "item:16000700": "关键道具。火山官邸牢镇内一间被小恶魔封印的房间底部，从尸体上拾取。",
    "item:16000610": "小盾。位于火山官邸牢镇与熔岩同一高度的墓碑旁，从坐着的尸体上拾取。",
    "item:16000070": "位于火山官邸区域的楼梯上，从躺着的尸体上拾取。",
    "item:16000540": "护符。位于火山官邸牢镇一间被小恶魔封印的房间上层。",
    "item:16000710": "击败火山官邸的神皮贵族后，在祭坛上取得。",
    "grace:160005": "位于拉卡德战斗区域入口附近。完成塔妮丝的三份暗杀委托后与她交谈，或穿过官邸隐藏区域并使用传送门，均可抵达。",
    "item:16000220": "消耗品。位于火山官邸牢镇一栋建筑外侧的尸体上。",
    "item:16000720": "多人游戏道具。加入火山官邸后，在放有官邸委托信的上锁客房内取得。",
    "item:1039420050": "湖之利耶尼亚东部，“高地瞭望塔”以东的战场上，在幽灵与骑士交战、装甲巨人出现的位置附近，打碎推车取得。",
    "item:1041380100": "黄金种子可增加红露滴圣杯瓶和蓝露滴圣杯瓶的使用次数，不会增加灵药圣杯瓶的数量。",
    "item:1037540150": "从格密尔火山（第1休息站）赐福向西北走，越过石柱桥，在接肢贵族附近的尸体上取得。武器位于最靠近梯子的尸体上。",
    "boss:1048400800": "地下室内有两名发狂南瓜头士兵。入口位于废墟东侧；击败他们后可进入藏宝室。",
    "poi:64474000": "位于桂奥尔龙墓一处破屋东南方的废墟。",
    "boss:31090800": "可选头目，位于火山洞窟最深处。",
    "boss:30120800": "丑恶地下墓地的双头目战，其中一名是调香师托莉夏。击败后获得“调香师托莉夏”骨灰。",
    "item:1035540010": "位于格密尔火山，击败守在尸体旁的手指怪后拾取。",
    "boss:1038520340": "位于威达姆废墟的积水区域。击败后获得死根与“提比亚的唤声”。",
}

TERMS = (
    ("弗拉斯克强化素材", "圣杯瓶强化素材"),
    ("消耗品项目", "消耗品"),
    ("多人项目", "多人游戏道具"),
    ("制作笔记项目", "制作笔记"),
    ("工艺材料", "制作材料"),
    ("工艺布特", "制作笔记"),
    ("精神 骨灰 强化素材(英语:骨灰 强化素材)", "骨灰强化素材"),
    ("灵骨灰", "灵灰"),
    ("升级的护符", "护符"),
    ("攻势的消耗品", "攻击类消耗品"),
    ("野外 头目", "野外头目"),
    ("选择头目", "可选头目"),
    ("伟大的敌人", "强敌"),
    ("物质。", "材料。"),
    ("武器装潢", "武器"),
    ("赐福点", "赐福"),
    ("篝火", "赐福"),
    ("灵魂气流号", "灵魂气流"),
    ("灰人", "骨灰"),
)


def polish(text: str) -> str:
    for old, new in TERMS:
        text = text.replace(old, new)
    text = text.replace("一具尸体上发现的", "尸体上拾取")
    text = text.replace("一具尸体上找到的", "尸体上拾取")
    text = text.replace("一具尸体上被发现的", "尸体上拾取")
    text = text.replace("发现于", "位于")
    text = re.sub(r"^(强化素材|消耗品|关键道具|护符|制作材料|卢恩消耗品|圣杯瓶强化素材)\n", r"\1。\n", text)
    text = re.sub(r"(?<=[\u3400-\u9fff])[ \t]+(?=[\u3400-\u9fff])", "", text)
    text = re.sub(r"[ \t]*\n[ \t]*", "\n", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"(?<!\d)[,.](?!\d)", "，", text)
    text = re.sub(r"(?<!\d)[.!?](?=\s|$)", "。", text)
    text = re.sub(r"。{2,}", "。", text)
    text = re.sub(r"，{2,}", "，", text)
    text = re.sub(r"\s+([，。；：])", r"\1", text)
    text = re.sub(r"([，。；：])\s+", r"\1", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def review(doc: dict, tips: dict) -> int:
    changed = 0
    for entry in doc["translations"].values():
        if entry.get("reviewed") or not entry.get("zh"):
            continue
        updated = polish(entry["zh"])
        if updated != entry["zh"]:
            entry["zh"] = updated
            changed += 1
    for marker, translated in ROUTES.items():
        if marker not in tips:
            continue
        source = tips[marker]["text"]
        key = sha256(source.encode("utf-8")).hexdigest()
        doc["translations"][key] = {"zh": translated, "reviewed": True}
    return changed


def main() -> None:
    doc = json.loads(PATH.read_text(encoding="utf-8"))
    tips = json.loads(TIPS_PATH.read_text(encoding="utf-8"))["tips"]
    changed = review(doc, tips)
    PATH.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Polished {changed} route notes")


if __name__ == "__main__":
    main()
