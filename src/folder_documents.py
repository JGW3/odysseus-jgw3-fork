"""Per-project document scopes.

A project (chat folder) whose policy has ``documents_private`` keeps its
documents to itself, mirroring private memories (src/folder_memory.py):

* A document created from a chat in such a project carries that project in
  ``Document.folder``. Other documents carry no folder: the shared pool.
* A chat in a private-documents project sees only its project's documents.
* Every other chat (another project, or none: "Main") sees the shared pool
  plus documents tagged with a project that no longer keeps them private.

These rules scope what the AI's document tools can find. The Library window
is the person's own view and still lists every document they own.
"""
from __future__ import annotations

from typing import Any, Optional

from src import folder_memory


def _private_projects(owner: Optional[str]) -> set[str]:
    return {name for name, policy in folder_memory.all_policies(owner).items() if policy.documents_private}


def folder_for_new_document(owner: Optional[str], session_id: Any) -> Optional[str]:
    """The ``folder`` a document created from this chat should carry."""
    folder = folder_memory.session_folder(session_id)
    if not folder:
        return None
    return folder if folder_memory.get_policy(owner, folder).documents_private else None


def scope_document_query(query, Document, owner: Optional[str], session_id: Any):
    """Limit a document query to what a chat in ``session_id``'s project may see.

    With no chat (``session_id`` empty) the query is returned unchanged, so
    callers outside a chat keep their current, owner-only scope.
    """
    if not str(session_id or "").strip():
        return query
    from sqlalchemy import or_

    folder = folder_memory.session_folder(session_id)
    private = _private_projects(owner)
    if folder and folder in private:
        return query.filter(Document.folder == folder)
    visible = [Document.folder.is_(None)]
    if folder:
        visible.append(Document.folder == folder)
    if private:
        visible.append(Document.folder.notin_(sorted(private)))
    else:
        visible.append(Document.folder.isnot(None))
    return query.filter(or_(*visible))


def document_visible(doc: Any, owner: Optional[str], session_id: Any) -> bool:
    """The same rule as ``scope_document_query``, for one loaded document."""
    if not str(session_id or "").strip():
        return True
    tag = str(getattr(doc, "folder", None) or "").strip()
    folder = folder_memory.session_folder(session_id)
    private = _private_projects(owner)
    if folder and folder in private:
        return tag == folder
    return not tag or tag == folder or tag not in private


def tag_project_documents(owner: Optional[str], folder: Any) -> int:
    """File a project's existing documents under it when it starts keeping
    documents private: every document linked to one of its chats. Returns
    the number tagged."""
    name = str(folder or "").strip()
    if not name:
        return 0
    from core.database import Document, Session as DbSession, SessionLocal

    db = SessionLocal()
    try:
        chats = db.query(DbSession.id).filter(DbSession.folder == name)
        if owner:
            chats = chats.filter(DbSession.owner == owner)
        chat_ids = [row[0] for row in chats.all()]
        if not chat_ids:
            return 0
        docs = db.query(Document).filter(Document.session_id.in_(chat_ids), Document.folder.is_(None))
        if owner:
            docs = docs.filter(Document.owner == owner)
        rows = docs.all()
        for row in rows:
            row.folder = name
        db.commit()
        return len(rows)
    finally:
        db.close()


def retag_session_documents(owner: Optional[str], session_id: Any, to_folder: Any) -> int:
    """Re-file a moved chat's documents under ``to_folder``'s rules."""
    sid = str(session_id or "").strip()
    if not sid:
        return 0
    name = str(to_folder or "").strip()
    tag = name if name and folder_memory.get_policy(owner, name).documents_private else None
    from core.database import Document, SessionLocal

    db = SessionLocal()
    try:
        docs = db.query(Document).filter(Document.session_id == sid)
        if owner:
            docs = docs.filter(Document.owner == owner)
        changed = 0
        for row in docs.all():
            if (row.folder or None) != tag:
                row.folder = tag
                changed += 1
        if changed:
            db.commit()
        return changed
    finally:
        db.close()


def rename_project_documents(owner: Optional[str], old: Any, new: Any) -> int:
    old_name, new_name = str(old or "").strip(), str(new or "").strip()
    if not old_name or not new_name or old_name == new_name:
        return 0
    from core.database import Document, SessionLocal

    db = SessionLocal()
    try:
        docs = db.query(Document).filter(Document.folder == old_name)
        if owner:
            docs = docs.filter(Document.owner == owner)
        rows = docs.all()
        for row in rows:
            row.folder = new_name
        db.commit()
        return len(rows)
    finally:
        db.close()


def documents_needing_move_choice(owner: Optional[str], session_id: Any, from_folder: Any, to_folder: Any) -> int:
    """How many of the chat's documents a move would change the visibility of."""
    def tag_for(folder):
        name = str(folder or "").strip()
        return name if name and folder_memory.get_policy(owner, name).documents_private else None

    if tag_for(from_folder) == tag_for(to_folder):
        return 0
    sid = str(session_id or "").strip()
    if not sid:
        return 0
    from core.database import Document, SessionLocal

    db = SessionLocal()
    try:
        docs = db.query(Document).filter(Document.session_id == sid)
        if owner:
            docs = docs.filter(Document.owner == owner)
        return docs.count()
    finally:
        db.close()
