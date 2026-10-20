"""Per-project document scopes (src/folder_documents.py).

A project with ``documents_private`` keeps the documents made in it to
itself: its chats see only those, and every other chat (other projects and
Main) can't see them. Everything else stays in the shared pool.
"""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import core.database as database
from core.database import Base, Document, DocumentVersion, Session as DbSession
from src import folder_documents as fd
from src import folder_memory as fm


@pytest.fixture
def db(monkeypatch, tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'app.db'}")
    Base.metadata.create_all(engine, tables=[DbSession.__table__, Document.__table__, DocumentVersion.__table__])
    factory = sessionmaker(bind=engine)
    monkeypatch.setattr(database, "SessionLocal", factory)
    store = {}
    monkeypatch.setattr(fm, "_load_prefs", lambda owner: dict(store.get(owner, {})))
    monkeypatch.setattr(fm, "_save_prefs", lambda owner, p: store.__setitem__(owner, dict(p)))
    s = factory()
    for sid, folder in (("main-chat", None), ("hw-chat", "Homework"), ("game-chat", "Game")):
        s.add(DbSession(id=sid, name=sid, endpoint_url="", model="", folder=folder, owner="u"))
    s.commit()
    s.close()
    return factory


def add_doc(factory, doc_id, session_id, folder=None):
    s = factory()
    s.add(Document(id=doc_id, session_id=session_id, title=doc_id, owner="u", folder=folder))
    s.commit()
    s.close()


def visible_ids(factory, session_id):
    s = factory()
    try:
        q = fd.scope_document_query(s.query(Document).filter(Document.owner == "u"), Document, "u", session_id)
        return sorted(d.id for d in q.all())
    finally:
        s.close()


def test_without_private_projects_every_chat_sees_every_document(db):
    add_doc(db, "recipe", "main-chat")
    add_doc(db, "essay", "hw-chat")
    for chat in ("main-chat", "hw-chat", "game-chat"):
        assert visible_ids(db, chat) == ["essay", "recipe"]
    assert fd.folder_for_new_document("u", "hw-chat") is None


def test_a_private_project_sees_only_its_own_and_nobody_else_sees_them(db):
    fm.set_policy("u", "Game", receive="all", share=True, documents_private=True)
    add_doc(db, "recipe", "main-chat")
    add_doc(db, "sheet", "game-chat", folder=fd.folder_for_new_document("u", "game-chat"))
    assert fd.folder_for_new_document("u", "game-chat") == "Game"
    assert visible_ids(db, "game-chat") == ["sheet"]
    assert visible_ids(db, "main-chat") == ["recipe"]
    assert visible_ids(db, "hw-chat") == ["recipe"]


def test_no_chat_keeps_the_owner_only_scope(db):
    fm.set_policy("u", "Game", receive="all", share=True, documents_private=True)
    add_doc(db, "sheet", "game-chat", folder="Game")
    assert visible_ids(db, None) == ["sheet"]


def test_turning_it_on_files_the_projects_existing_documents(db):
    add_doc(db, "old sheet", "game-chat")
    add_doc(db, "recipe", "main-chat")
    fm.set_policy("u", "Game", receive="all", share=True, documents_private=True)
    assert fd.tag_project_documents("u", "Game") == 1
    assert visible_ids(db, "main-chat") == ["recipe"]
    assert visible_ids(db, "game-chat") == ["old sheet"]


def test_turning_it_off_returns_the_documents_to_the_shared_pool(db):
    fm.set_policy("u", "Game", receive="all", share=True, documents_private=True)
    add_doc(db, "sheet", "game-chat", folder="Game")
    fm.set_policy("u", "Game", receive="all", share=True, documents_private=False)
    assert visible_ids(db, "main-chat") == ["sheet"]


def test_moving_a_chat_moves_its_documents_when_asked(db):
    fm.set_policy("u", "Game", receive="all", share=True, documents_private=True)
    add_doc(db, "notes", "main-chat")
    assert fd.documents_needing_move_choice("u", "main-chat", None, "Game") == 1
    assert fd.documents_needing_move_choice("u", "main-chat", None, "Homework") == 0
    assert fd.retag_session_documents("u", "main-chat", "Game") == 1
    assert visible_ids(db, "hw-chat") == []


def test_renaming_a_project_keeps_its_documents(db):
    fm.set_policy("u", "Game", receive="all", share=True, documents_private=True)
    add_doc(db, "sheet", "game-chat", folder="Game")
    assert fd.rename_project_documents("u", "Game", "Life Sim") == 1


def test_document_visible_matches_the_query(db):
    fm.set_policy("u", "Game", receive="all", share=True, documents_private=True)
    sheet = Document(id="sheet", folder="Game")
    shared = Document(id="recipe", folder=None)
    assert fd.document_visible(sheet, "u", "game-chat")
    assert not fd.document_visible(shared, "u", "game-chat")
    assert not fd.document_visible(sheet, "u", "main-chat")
    assert fd.document_visible(shared, "u", "main-chat")


def test_the_policy_keeps_documents_private_when_memory_settings_change(db):
    fm.set_policy("u", "Game", receive="none", share=False, documents_private=True)
    policy = fm.set_policy("u", "Game", receive="all", share=True)
    assert policy.documents_private
    assert not policy.is_default


def test_memories_from_a_projects_chats_are_filed_when_it_turns_private():
    entries = [
        {"id": "1", "session_id": "game-chat"},
        {"id": "2", "session_id": "main-chat"},
        {"id": "3", "session_id": "game-chat", "folder": "Other"},
    ]
    assert fm.tag_chat_memories(entries, {"game-chat"}, "Game") == 1
    assert entries[0]["folder"] == "Game"
    assert "folder" not in entries[1]
    assert entries[2]["folder"] == "Other"


class _FakeMemory:
    def __init__(self, entries):
        self.entries = entries

    def load(self, owner=None):
        return [e for e in self.entries if owner is None or e.get("owner") == owner]

    def load_all_for_update(self):
        return [dict(e) for e in self.entries]

    def save(self, entries):
        self.entries = entries


class _FakeVector:
    healthy = True

    def __init__(self):
        self.removed = []

    def remove(self, memory_id):
        self.removed.append(memory_id)


def _delete_client(monkeypatch, memory, vector):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from routes import folder_routes
    monkeypatch.setattr(folder_routes, "SessionLocal", database.SessionLocal)
    monkeypatch.setattr(folder_routes, "effective_user", lambda request: "u")
    app = FastAPI()
    app.include_router(folder_routes.setup_folder_routes(memory, memory_vector=vector))
    return TestClient(app)


def _project_state(factory):
    s = factory()
    try:
        chats = {c.id: c.folder for c in s.query(DbSession).all()}
        docs = {d.id: d.folder for d in s.query(Document).all()}
        return chats, docs
    finally:
        s.close()


def test_deleting_a_project_and_moving_its_chats_to_main(db, monkeypatch):
    fm.set_policy("u", "Game", receive="none", share=False, documents_private=True)
    add_doc(db, "sheet", "game-chat", folder="Game")
    memory = _FakeMemory([{"id": "m1", "owner": "u", "folder": "Game", "text": "a"},
                          {"id": "m2", "owner": "u", "text": "b"}])
    vector = _FakeVector()
    client = _delete_client(monkeypatch, memory, vector)
    res = client.delete("/api/folders/Game?mode=move")
    assert res.status_code == 200 and res.json()["chats_moved"] == 1
    chats, docs = _project_state(db)
    assert chats["game-chat"] is None and docs["sheet"] is None
    assert [e for e in memory.entries if e["id"] == "m1"][0].get("folder") is None
    assert vector.removed == []
    assert "Game" not in fm.all_policies("u")


def test_deleting_a_project_and_everything_in_it(db, monkeypatch):
    fm.set_policy("u", "Game", receive="none", share=False, documents_private=True)
    add_doc(db, "sheet", "game-chat", folder="Game")
    add_doc(db, "recipe", "main-chat")
    memory = _FakeMemory([{"id": "m1", "owner": "u", "folder": "Game", "text": "a"},
                          {"id": "m2", "owner": "u", "text": "b"},
                          {"id": "m3", "owner": "other", "folder": "Game", "text": "c"}])
    vector = _FakeVector()
    client = _delete_client(monkeypatch, memory, vector)
    assert client.get("/api/folders/Game/chat-ids").json()["chat_ids"] == ["game-chat"]
    res = client.delete("/api/folders/Game?mode=everything")
    assert res.status_code == 200
    _, docs = _project_state(db)
    assert "sheet" not in docs and "recipe" in docs
    assert sorted(e["id"] for e in memory.entries) == ["m2", "m3"]   # another owner's memory is untouched
    assert vector.removed == ["m1"]
    assert client.delete("/api/folders/Game?mode=nope").status_code == 400
