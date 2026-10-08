"""Project memory scopes through the real read/write paths.

Uses a real MemoryManager on a temp dir; only the model call, the project
lookup and the prefs store are faked.
"""
import json

import pytest

from src import folder_memory as fm
from src.memory import MemoryManager


@pytest.fixture
def store(tmp_path, monkeypatch):
    prefs = {}
    monkeypatch.setattr(fm, "_load_prefs", lambda owner: dict(prefs.get(owner, {})))
    monkeypatch.setattr(fm, "_save_prefs", lambda owner, p: prefs.__setitem__(owner, dict(p)))
    chats = {"game-chat": "Game", "hw-chat": "Homework", "loose-chat": None}
    monkeypatch.setattr(fm, "session_folder", lambda sid: chats.get(str(sid or "")))
    fm.set_policy("u", "Game", receive="none", share=False, now=1)
    manager = MemoryManager(str(tmp_path))
    manager.save([
        # Pinned identity memories are injected into every chat they're
        # visible to, so they are the leak a project scope must stop.
        {"id": "hw1", "text": "Studies calculus at university", "owner": "u", "timestamp": 5,
         "session_id": "hw-chat", "category": "identity", "uses": 0, "pinned": True},
        {"id": "g1", "text": "Plays a character named Rae", "owner": "u", "timestamp": 6,
         "session_id": "game-chat", "category": "identity", "uses": 0, "folder": "Game", "pinned": True},
    ])
    return manager


@pytest.mark.asyncio
async def test_memory_tool_lists_and_edits_only_in_scope(store, monkeypatch):
    from src import ai_interaction
    monkeypatch.setattr(ai_interaction, "_memory_manager", store)
    monkeypatch.setattr(ai_interaction, "_memory_vector", None)
    game = await ai_interaction.do_manage_memory("list", session_id="game-chat", owner="u")
    assert "Rae" in game["results"] and "calculus" not in game["results"]
    loose = await ai_interaction.do_manage_memory("list", session_id="loose-chat", owner="u")
    assert "calculus" in loose["results"] and "Rae" not in loose["results"]
    blocked = await ai_interaction.do_manage_memory("edit\nhw1\nchanged", session_id="game-chat", owner="u")
    assert "not found" in blocked["error"]
    gone = await ai_interaction.do_manage_memory("delete\ng1", session_id="hw-chat", owner="u")
    assert "not found" in gone["error"]
    assert {m["id"] for m in store.load("u")} == {"hw1", "g1"}


@pytest.mark.asyncio
async def test_memory_tool_add_in_contained_project_stays_private(store, monkeypatch):
    from src import ai_interaction
    monkeypatch.setattr(ai_interaction, "_memory_manager", store)
    monkeypatch.setattr(ai_interaction, "_memory_vector", None)
    await ai_interaction.do_manage_memory("add\nRae owes the landlord rent\nfact", session_id="game-chat", owner="u")
    added = next(m for m in store.load("u") if "landlord" in m["text"])
    assert added["folder"] == "Game" and added["session_id"] == "game-chat"


def test_chat_prompt_memory_is_scoped(store):
    from src.chat_processor import ChatProcessor
    processor = ChatProcessor(store, personal_docs_manager=None, memory_vector=None)

    class Sess:
        def __init__(self, sid):
            self.id = sid
            self.history = []

    def injected(sid):
        preface, _, _ = processor.build_context_preface(
            "Help me plan around my exam, and remind me about Rae.", Sess(sid), use_rag=False, use_memory=True,
            owner="u", use_skills=False,
        )
        return json.dumps(preface)

    assert "Rae" not in injected("loose-chat") and "calculus" in injected("loose-chat")
    assert "calculus" not in injected("game-chat") and "Rae" in injected("game-chat")


@pytest.mark.asyncio
async def test_tidy_never_merges_across_scopes(store, monkeypatch):
    from services.memory import memory_extractor
    seen_batches = []

    async def fake_llm(url, model, messages, **kwargs):
        batch = json.loads(messages[-1]["content"])
        seen_batches.append(sorted(m["id"] for m in batch))
        # Pretend the model merges everything it was given into the first id.
        merged = " / ".join(m["text"] for m in batch)
        return json.dumps([{"id": batch[0]["id"], "text": merged, "category": "fact"}])

    monkeypatch.setattr("src.llm_core.llm_call_async", fake_llm)
    store.save(store.load_all() + [
        {"id": "hw2", "text": "Takes Physics 2", "owner": "u", "timestamp": 7, "session_id": "hw-chat",
         "category": "fact", "uses": 0},
        {"id": "g2", "text": "Rae lives in Toronto", "owner": "u", "timestamp": 8, "session_id": "game-chat",
         "category": "fact", "uses": 0, "folder": "Game"},
    ])
    await memory_extractor.audit_memories(store, None, "http://x", "m", owner="u")
    assert sorted(seen_batches) == [["g1", "g2"], ["hw1", "hw2"]]
    after = {m["id"]: m for m in store.load("u")}
    shared_text = " ".join(m["text"] for m in after.values() if not m.get("folder"))
    assert "Rae" not in shared_text
    assert all(m.get("folder") == "Game" for m in after.values() if "Rae" in m["text"])
