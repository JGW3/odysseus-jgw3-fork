"""Per-project memory scopes (src/folder_memory.py).

A project's policy has two settings: which shared memories it receives
(all / snapshot / none) and whether its own memories join the shared pool.
"""
import pytest

from src import folder_memory as fm


@pytest.fixture
def prefs(monkeypatch):
    store = {}
    monkeypatch.setattr(fm, "_load_prefs", lambda owner: dict(store.get(owner, {})))
    monkeypatch.setattr(fm, "_save_prefs", lambda owner, p: store.__setitem__(owner, dict(p)))
    return store


def mem(text, *, folder=None, ts=100, session="s1"):
    entry = {"id": text, "text": text, "timestamp": ts, "session_id": session, "owner": "u"}
    if folder:
        entry["folder"] = folder
    return entry


def visible(entries, folder):
    return [e["text"] for e in fm.filter_visible(entries, "u", folder)]


def test_existing_folders_and_folderless_chats_keep_todays_behaviour(prefs):
    entries = [mem("a"), mem("b")]
    assert fm.get_policy("u", "Homework").is_default
    assert visible(entries, "Homework") == ["a", "b"]
    assert visible(entries, None) == ["a", "b"]
    assert fm.folder_for_new_memory("u", "Homework") is None      # still feeds the shared pool


def test_fresh_contained_project_sees_only_its_own(prefs):
    fm.set_policy("u", "Game", receive="none", share=False, now=200)
    entries = [mem("homework fact"), mem("game fact", folder="Game")]
    assert visible(entries, "Game") == ["game fact"]
    assert fm.folder_for_new_memory("u", "Game") == "Game"


def test_private_memories_never_leak_to_other_chats(prefs):
    fm.set_policy("u", "Game", receive="all", share=False)
    entries = [mem("shared"), mem("game secret", folder="Game")]
    assert visible(entries, None) == ["shared"]                   # folderless
    assert visible(entries, "Homework") == ["shared"]             # another project


def test_snapshot_project_keeps_what_existed_then(prefs):
    fm.set_policy("u", "Novel", receive="snapshot", share=False, now=500)
    entries = [mem("old shared", ts=400), mem("new shared", ts=600), mem("novel own", folder="Novel", ts=700)]
    assert visible(entries, "Novel") == ["old shared", "novel own"]


def test_keep_receiving_but_private(prefs):
    fm.set_policy("u", "Taxes", receive="all", share=False)
    entries = [mem("old", ts=1), mem("brand new", ts=10**10), mem("taxes own", folder="Taxes")]
    assert visible(entries, "Taxes") == ["old", "brand new", "taxes own"]
    assert visible(entries, None) == ["old", "brand new"]


def test_switching_a_project_to_share_releases_its_memories(prefs):
    fm.set_policy("u", "Game", receive="none", share=False)
    entries = [mem("game fact", folder="Game")]
    assert visible(entries, None) == []
    fm.set_policy("u", "Game", receive="none", share=True)
    assert visible(entries, None) == ["game fact"]


def test_snapshot_time_is_kept_while_staying_in_snapshot(prefs):
    first = fm.set_policy("u", "Novel", receive="snapshot", share=False, now=500)
    again = fm.set_policy("u", "Novel", receive="snapshot", share=True, now=900)
    assert first.snapshot_at == again.snapshot_at == 500
    assert first.created_at == again.created_at == 500
    reset = fm.set_policy("u", "Novel", receive="all", share=True, now=950)
    assert reset.snapshot_at == 0


def test_invalid_policy_rejected(prefs):
    with pytest.raises(ValueError):
        fm.set_policy("u", "X", receive="sometimes", share=True)
    with pytest.raises(ValueError):
        fm.set_policy("u", "  ", receive="all", share=True)


def test_move_only_asks_when_visibility_changes(prefs):
    fm.set_policy("u", "Game", receive="none", share=False)
    entries = [mem("a", session="chat-1"), mem("b", session="chat-1"), mem("c", session="other")]
    assert fm.move_needs_choice(entries, "u", "chat-1", "Homework", "Recipes") == 0   # both shared
    assert fm.move_needs_choice(entries, "u", "chat-1", None, "Game") == 2
    assert fm.move_needs_choice(entries, "u", "chat-2", None, "Game") == 0            # no memories


def test_moving_memories_follows_the_destination_rules(prefs):
    fm.set_policy("u", "Game", receive="none", share=False)
    entries = [mem("a", session="chat-1"), mem("c", session="other")]
    assert fm.retag_for_move(entries, "u", "chat-1", "Game") == 1
    assert entries[0]["folder"] == "Game" and "folder" not in entries[1]
    assert fm.retag_for_move(entries, "u", "chat-1", None) == 1
    assert "folder" not in entries[0]


def test_tag_new_memory_uses_the_chats_project(prefs, monkeypatch):
    fm.set_policy("u", "Game", receive="none", share=False)
    monkeypatch.setattr(fm, "session_folder", lambda sid: {"g": "Game", "h": "Homework"}.get(sid))
    assert fm.tag_new_memory({"text": "x"}, "u", "g")["folder"] == "Game"
    assert "folder" not in fm.tag_new_memory({"text": "y", "folder": "stale"}, "u", "h")


def test_rename_carries_the_policy(prefs):
    fm.set_policy("u", "Old", receive="none", share=False)
    fm.rename_policy("u", "Old", "New")
    assert fm.get_policy("u", "New").receive == "none"
    assert fm.get_policy("u", "Old").is_default
