from eldenringtool.core.tips import source_key, tip_text


def test_chinese_tips_preferred_without_destroying_english():
    tip = {"text": "In a chest.", "credit": "Source"}
    cache = {source_key(tip["text"]): {"zh": "在宝箱中。"}}
    assert tip_text(tip, cache) == "在宝箱中。"
    assert tip_text(tip, cache, "en") == "In a chest."
    assert tip["text"] == "In a chest."
    assert tip_text({**tip, "texts": {"zh": "打开宝箱取得。"}}, cache) == "打开宝箱取得。"
    assert tip_text({"text": {"en": "Chest", "zh": "宝箱"}}) == "宝箱"


def test_stale_translation_is_not_applied_to_changed_route():
    cache = {source_key("In a chest."): {"zh": "在宝箱中。"}}
    assert tip_text({"text": "Dropped by an enemy."}, cache) == "Dropped by an enemy."
    assert tip_text(None, cache) == ""


def test_local_route_cache_has_chinese_for_every_existing_note():
    import json
    import re
    from pathlib import Path
    import pytest
    data = Path(__file__).resolve().parents[1] / 'data'
    if not (data / 'tips.json').exists() or not (data / 'tips-zh.json').exists():
        pytest.skip('Locally generated route data is not installed')
    tips = json.loads((data / 'tips.json').read_text(encoding='utf-8'))['tips']
    translations = json.loads((data / 'tips-zh.json').read_text(encoding='utf-8'))['translations']
    for ident, tip in tips.items():
        text = tip_text(tip, translations)
        assert re.search(r'[\u3400-\u9fff]', text), ident
        assert '原始内容存档' not in text, ident
        assert '{\\fn' not in text, ident
        # Stats, scaling ranks, D's name and quantity multipliers are intentional.
        assert set(re.findall(r'[A-Za-z]+', text)) <= {'HP', 'FP', 'x', 'X', 'D', 'S'}, (ident, text)
