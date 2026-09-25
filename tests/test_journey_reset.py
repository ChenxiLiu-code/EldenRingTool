import pytest

from eldenringtool.core.state_store import StateStore


def test_reset_is_scoped_persistent_and_blocks_legacy_fallback(tmp_path):
    path = tmp_path / 'state.json'
    store = StateStore(path)
    hero = {'slot': 0, 'name': 'Hero'}
    other = {'slot': 1, 'name': 'Other'}
    save = 'account/save.sl2'
    store.data['checked'][store.quest_id(hero, 'q', 'legacy')] = True
    store.data['checked']['old-map'] = True
    for account, character in ((save, hero), (save, other), ('other/save.sl2', hero)):
        store.set_marker_checked(account, character, 'm', True)
        store.set_quest_done(account, character, 'q', 's', True)
    store.set_display_setting(save, hero, 'mapHideCompleted', False)
    store.reset_manual_marks(save, hero)
    store = StateStore(path)
    assert not store.marker_checked(save, hero, 'm')
    assert not store.quest_done(save, hero, 'q', 's')
    assert not store.quest_done(save, hero, 'q', 'legacy')
    assert store.quest_done('other/save.sl2', hero, 'q', 'legacy')
    assert store.display_settings(save, hero)['mapHideCompleted'] is False
    assert store.legacy_marker_ids() == ['old-map']
    for account, character in ((save, other), ('other/save.sl2', hero)):
        assert store.marker_checked(account, character, 'm')
        assert store.quest_done(account, character, 'q', 's')
    store.set_quest_done(save, hero, 'q', 's', True)
    assert store.quest_done(save, hero, 'q', 's')


def test_reset_write_failure_preserves_marks(tmp_path, monkeypatch):
    store = StateStore(tmp_path / 'state.json')
    hero = {'slot': 0, 'name': 'Hero'}
    store.set_marker_checked('account/save.sl2', hero, 'm', True)
    def fail():
        raise OSError('disk unavailable')
    monkeypatch.setattr(store, 'save', fail)
    with pytest.raises(OSError):
        store.reset_manual_marks('account/save.sl2', hero)
    assert store.marker_checked('account/save.sl2', hero, 'm')
