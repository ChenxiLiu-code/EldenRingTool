from eldenringtool.core.quest_engine import evaluate_quest


def test_multiple_automatic_steps_backfill_unchecked_guides():
    quest = {"id": "q", "steps": [
        {"id": "guide", "guideOnly": True},
        {"id": "first", "completeWhen": {"flag": 1}},
        {"id": "second_guide", "guideOnly": True},
        {"id": "second", "completeWhen": {"flag": 2}},
        {"id": "third", "completeWhen": {"marker": "reward"}},
        {"id": "future_guide", "guideOnly": True},
        {"id": "future", "completeWhen": {"flag": 3}},
    ]}
    for checked in (False, True, False):
        result = evaluate_quest(quest, {1: True, 2: True}, {"reward"},
                                lambda q, s: checked and s == "guide")
        rows = {s["id"]: s for s in result["steps"]}
        assert all(rows[s]["complete"] for s in ("guide", "first", "second_guide", "second", "third"))
        assert rows["guide"]["source"] == ("manual" if checked else "inferred")
        assert rows["second_guide"]["source"] == "inferred"
        assert all(rows[s]["source"] == "auto" for s in ("first", "second", "third"))
        assert not rows["future_guide"]["complete"]
        assert rows["future"]["available"]


def test_later_progress_does_not_choose_branches_or_optional_guides():
    quest = {"id": "q", "steps": [
        {"id": "optional", "guideOnly": True, "optional": True},
        {"id": "opt_out", "guideOnly": True, "inferFromLater": False},
        {"id": "a", "guideOnly": True, "exclusiveGroup": "route", "exclusiveOption": "a"},
        {"id": "b", "guideOnly": True, "exclusiveGroup": "route", "exclusiveOption": "b"},
        {"id": "auto", "completeWhen": {"flag": 1}},
    ]}
    result = evaluate_quest(quest, {1: True})
    assert all(not s["complete"] and not s["missed"] for s in result["steps"][:-1])


def test_explicit_inference_and_supersession_rules_take_priority():
    quest = {"id": "q", "steps": [
        {"id": "guide", "guideOnly": True, "impliedBySteps": ["end"]},
        {"id": "skippable", "guideOnly": True, "supersededBySteps": ["end"]},
        {"id": "unrelated", "completeWhen": {"flag": 1}},
        {"id": "end", "completeWhen": {"flag": 2}},
    ]}
    assert not evaluate_quest(quest, {1: True})["steps"][0]["complete"]
    result = evaluate_quest(quest, {2: True})
    assert result["steps"][0]["inferred"]
    assert result["steps"][1]["superseded"]


def test_inference_is_recomputed_for_each_save_and_character():
    quest = {"id": "q", "steps": [
        {"id": "guide", "guideOnly": True},
        {"id": "auto", "completeWhen": {"flag": 1}},
    ]}
    assert evaluate_quest(quest, {1: True})["steps"][0]["complete"]
    assert not evaluate_quest(quest, {})["steps"][0]["complete"]


def test_thops_completed_rewards_recover_missing_intermediate_flags():
    import json
    from pathlib import Path
    doc = json.loads((Path(__file__).resolve().parents[1] / 'data/quests/base_game.json').read_text(encoding='utf-8'))
    quest = next(q for q in doc['quests'] if q['id'] == 'thops')
    # Observed save state: the reward is retained, intermediate flags are off.
    for checked in (False, True):
        result = evaluate_quest(quest, {1039399206: True, 1039392704: False,
                                       14002660: False, 400360: True, 400362: True},
                                manual_done=lambda q, s: checked and s == 'second_key')
        assert result['status'] == 'completed'
        assert all(row['complete'] for row in result['steps'])
        assert result['steps'][2]['source'] == 'inferred'
        assert result['steps'][3]['source'] == 'auto'
    # The bell bearing alone can also be obtained by killing Thops early.
    result = evaluate_quest(quest, {400360: True})
    assert result['status'] != 'completed'
    assert not any(row['complete'] for row in result['steps'])


def test_thops_key_handover_backfills_guide_before_final_reward():
    import json
    from pathlib import Path
    doc = json.loads((Path(__file__).resolve().parents[1] / 'data/quests/base_game.json').read_text(encoding='utf-8'))
    quest = next(q for q in doc['quests'] if q['id'] == 'thops')
    result = evaluate_quest(quest, {1039392704: True})
    assert all(row['complete'] for row in result['steps'][:3])
    assert result['steps'][3]['available']
