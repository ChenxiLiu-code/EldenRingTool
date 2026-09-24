"""Build an offline Chinese route-note cache using an Argos en_zh model.

Requires the optional ctranslate2 and sentencepiece packages. Run with
--model pointing to the extracted translate-en_zh-1_9 directory. Neither the
model nor these dependencies are needed by the application itself.
Original route notes and source credits remain untouched in tips.json.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from eldenringtool.core.tips import source_key


class PlainText(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []

    def handle_data(self, data):
        self.parts.append(data)

    def handle_starttag(self, tag, attrs):
        if tag in {"br", "p", "li", "div"}:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in {"p", "li", "div"}:
            self.parts.append("\n")


def plain_text(text):
    parser = PlainText()
    parser.feed(text)
    return re.sub(r"[ \t]+", " ", "".join(parser.parts)).strip()


def polish(text, names):
    # Remove spurious subtitle/Wikipedia formatting emitted by the small NMT
    # model. These are not present in the route notes and must not reach QML.
    text = re.sub(r'\{\\[^}]*\}', '', text)
    text = re.sub(r'[（(]原始内容存档[^)）]*[)）][.。]?\s*', '', text)
    terms = {en.lower(): zh for en, zh in names.items()}
    pattern = re.compile(r'(?<![A-Za-z])(?:' + '|'.join(re.escape(n) for n in sorted(terms, key=len, reverse=True)) + r')(?![A-Za-z])', re.I)
    text = pattern.sub(lambda m: terms[m.group().lower()], text)
    text = text.replace('失败后离开', '击败后掉落').replace('产卵', '出现')
    return text.strip()


def glossary():
    names = {}
    for filename, field in (("markers.json", "markers"), ("items.json", "markers"),
                            ("catalog.json", "items")):
        path = ROOT / "data" / filename
        if not path.exists():
            continue
        for row in json.loads(path.read_text(encoding="utf-8")).get(field, []):
            texts = row.get("names") or {}
            en, zh = texts.get("en"), texts.get("zh")
            if en and zh and en != zh and re.search(r"[\u3400-\u9fff]", zh):
                names[en] = zh
    for path in (ROOT / 'data/quests').glob('*.json'):
        for quest in json.loads(path.read_text(encoding='utf-8')).get('quests', []):
            for key in ('name', 'character'):
                texts = quest.get(key)
                if isinstance(texts, dict) and texts.get('en') and texts.get('zh'):
                    names[texts['en']] = texts['zh']
    names.update(json.loads((ROOT / 'data/tip-glossary-zh.json').read_text(encoding='utf-8')))
    return names


def main():
    import ctranslate2
    import sentencepiece

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--model", type=Path, required=True)
    ap.add_argument("--tips", type=Path, default=ROOT / "data" / "tips.json")
    ap.add_argument("--out", type=Path, default=ROOT / "data" / "tips-zh.json")
    ap.add_argument("--refresh", action="store_true", help="Regenerate existing machine translations")
    args = ap.parse_args()
    tokenizer = sentencepiece.SentencePieceProcessor(model_file=str(args.model / "sentencepiece.model"))
    translator = ctranslate2.Translator(str(args.model / "model"), device="cpu", compute_type="int8", intra_threads=4)

    def translate(texts):
        results = translator.translate_batch([tokenizer.encode(t, out_type=str) for t in texts],
                                             beam_size=4, max_batch_size=32, max_decoding_length=512)
        return [tokenizer.decode(r.hypotheses[0]).strip() for r in results]

    tips = json.loads(args.tips.read_text(encoding="utf-8")).get("tips", {})
    originals = list(dict.fromkeys(t["text"] for t in tips.values() if isinstance(t.get("text"), str)))
    cache = json.loads(args.out.read_text(encoding="utf-8")) if args.out.exists() else {}
    translations = cache.setdefault("translations", {})
    cache.update(schema=1, language="zh", method="Argos en_zh 1.9; game-name glossary",
                 note="Local translations of tips.json; original source credits and usage restrictions apply.")
    pending = [s for s in originals if not translations.get(source_key(s), {}).get('reviewed')
               and (args.refresh or not translations.get(source_key(s), {}).get("zh"))]
    names = glossary()
    pattern = re.compile(r"(?<!\w)(?:" + "|".join(re.escape(n) for n in sorted(names, key=len, reverse=True)) + r")(?!\w)", re.I) if names else None
    lower_names = {n.lower(): (n, zh) for n, zh in names.items()}
    # Familiar proper nouns survive this small translation model far better
    # than unknown game names or artificial identifiers. Restore the exact
    # in-game Chinese names after translating each sentence. If a name is
    # dropped, translate the surrounding clauses separately instead.
    placeholders = [('London', '伦敦'), ('Paris', '巴黎'), ('Berlin', '柏林'),
                    ('Tokyo', '东京'), ('Sydney', '悉尼'), ('Madrid', '马德里'),
                    ('Moscow', '莫斯科'), ('Boston', '波士顿'), ('Chicago', '芝加哥'),
                    ('Toronto', '多伦多'), ('Oxford', '牛津'), ('Cambridge', '剑桥')]

    def prepare(part):
        replacements = []
        def replace(match):
            index = len(replacements)
            if index >= len(placeholders):
                return match.group()
            replacements.append(lower_names[match.group().lower()][1])
            return placeholders[index][0]
        protected = pattern.sub(replace, part) if pattern else part
        protected = re.sub(r'\blooted\b', 'obtained', protected, flags=re.I)
        protected = re.sub(r'\bloot\b', 'items', protected, flags=re.I)
        protected = re.sub(r'\bchest\b', 'treasure chest', protected, flags=re.I)
        return protected, replacements

    def restore(part, translated, replacements):
        restored = translated
        for (en, zh), target in zip(placeholders, replacements):
            if en not in restored and zh not in restored:
                # Preserve every named location/item even when the model
                # fails to carry its placeholder into the result.
                matches = list(pattern.finditer(part))
                pieces, cursor = [], 0
                for match in matches:
                    if match.start() > cursor:
                        pieces.extend(translate([part[cursor:match.start()]]))
                    pieces.append(lower_names[match.group().lower()][1])
                    cursor = match.end()
                if cursor < len(part):
                    pieces.extend(translate([part[cursor:]]))
                return ''.join(pieces)
            restored = restored.replace(en, target).replace(zh, target)
        return restored

    def save():
        args.out.parent.mkdir(parents=True, exist_ok=True)
        tmp = args.out.with_suffix(".tmp")
        tmp.write_text(json.dumps(cache, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        tmp.replace(args.out)

    for start in range(0, len(pending), 32):
        batch = pending[start:start + 32]
        parts = [re.split(r"(?<=[.!?])\s+|\n+", plain_text(s)) for s in batch]
        prepared = [prepare(part) for row in parts for part in row]
        translated = iter(translate([part for part, _ in prepared]))
        prepared_iter = iter(prepared)
        for source, row in zip(batch, parts):
            zh = "\n".join(restore(part, next(translated), next(prepared_iter)[1]) for part in row)
            if not plain_text(source):
                zh = "原始说明未包含文字。"
            zh = zh.replace("▁", " ").replace(" ⁇ ", " ").strip()
            if not zh:
                raise ValueError(f"Empty translation for {source_key(source)}")
            translations[source_key(source)] = {"zh": zh}
        save()
        print(f"Translated {min(start + 32, len(pending))}/{len(pending)}", flush=True)
    for entry in translations.values():
        if not entry.get('reviewed'):
            entry['zh'] = polish(entry['zh'], names)
    save()
    print(f"Saved {len(translations)} translations to {args.out}")


if __name__ == "__main__":
    main()
