"""Projects (chat folders) and their settings: memory (src/folder_memory.py)
and documents (src/folder_documents.py)."""
import logging

from fastapi import APIRouter, HTTPException, Request

from core.database import Session as DbSession, SessionLocal
from src import folder_documents, folder_memory
from src.auth_helpers import effective_user
from src.memory import MemoryManager, MemoryStoreUnreadable

logger = logging.getLogger(__name__)


def _folder_chat_counts(user):
    db = SessionLocal()
    try:
        query = db.query(DbSession.folder).filter(DbSession.folder.isnot(None))
        if user:
            query = query.filter(DbSession.owner == user)
        counts = {}
        for (folder,) in query.all():
            name = str(folder or "").strip()
            if name:
                counts[name] = counts.get(name, 0) + 1
        return counts
    finally:
        db.close()


def _session_folder(user, session_id):
    db = SessionLocal()
    try:
        query = db.query(DbSession).filter(DbSession.id == session_id)
        if user:
            query = query.filter(DbSession.owner == user)
        row = query.first()
        if row is None:
            raise HTTPException(404, "Chat not found")
        return str(row.folder or "").strip() or None
    finally:
        db.close()


def apply_memory_move(memory_manager: MemoryManager, user, session_id, to_folder, choice) -> int:
    """Re-file a moved chat's memories when the user chose to move them."""
    if str(choice or "").strip().lower() != "move":
        return 0
    try:
        entries = memory_manager.load_all_for_update()
    except MemoryStoreUnreadable as error:
        logger.error("Memory store unreadable; not moving memories for %s: %s", session_id, error)
        return 0
    owned = [e for e in entries if not user or e.get("owner") == user]
    changed = folder_memory.retag_for_move(owned, user, session_id, to_folder)
    if changed:
        memory_manager.save(entries)
    return changed


def apply_document_move(user, session_id, to_folder, choice) -> int:
    """Re-file a moved chat's documents when the user chose to move them."""
    if str(choice or "").strip().lower() != "move":
        return 0
    return folder_documents.retag_session_documents(user, session_id, to_folder)


def _private_document_counts(user):
    from core.database import Document
    db = SessionLocal()
    try:
        query = db.query(Document.folder).filter(Document.folder.isnot(None))
        if user:
            query = query.filter(Document.owner == user)
        counts = {}
        for (folder,) in query.all():
            name = str(folder or "").strip()
            if name:
                counts[name] = counts.get(name, 0) + 1
        return counts
    finally:
        db.close()


def _project_chat_ids(user, folder):
    db = SessionLocal()
    try:
        query = db.query(DbSession.id).filter(DbSession.folder == folder)
        if user:
            query = query.filter(DbSession.owner == user)
        return {row[0] for row in query.all()}
    finally:
        db.close()


def _policy_dict(policy):
    return {
        "receive": policy.receive, "share": policy.share,
        "created_at": policy.created_at, "snapshot_at": policy.snapshot_at,
    }


def setup_folder_routes(memory_manager: MemoryManager, memory_vector=None):
    router = APIRouter(prefix="/api/folders", tags=["folders"])

    @router.get("")
    def list_folders(request: Request):
        user = effective_user(request)
        counts = _folder_chat_counts(user)
        policies = folder_memory.all_policies(user)
        entries = memory_manager.load(user)
        private = {}
        for entry in entries:
            tag = str(entry.get("folder") or "").strip()
            if tag:
                private[tag] = private.get(tag, 0) + 1
        private_docs = _private_document_counts(user)
        names = sorted(set(counts) | set(policies), key=str.casefold)
        default = folder_memory.DEFAULT_POLICY
        return {"folders": [
            {
                "name": name,
                "chats": counts.get(name, 0),
                "private_memories": private.get(name, 0),
                "private_documents": private_docs.get(name, 0),
                "memory": _policy_dict(policies.get(name, default)),
                "documents_private": policies.get(name, default).documents_private,
                "description": policies.get(name, default).description,
            }
            for name in names
        ]}

    def _save_settings(request: Request, name: str, body: dict):
        user = effective_user(request)
        folder = name.strip()
        before = folder_memory.get_policy(user, folder)
        documents_private = body.get("documents_private")
        description = body.get("description")
        try:
            policy = folder_memory.set_policy(
                user, folder, receive=str(body.get("receive") or "all"), share=body.get("share") is not False,
                documents_private=None if documents_private is None else documents_private is True,
                description=None if description is None else str(description))
        except ValueError as error:
            raise HTTPException(400, str(error))
        # Turning compartmentalization on files what the project's chats
        # already made under it, so nothing it made stays in the shared pool.
        tagged_memories = tagged_documents = 0
        if before.share and not policy.share:
            tagged_memories = _tag_project_memories(user, folder)
        if policy.documents_private and not before.documents_private:
            tagged_documents = folder_documents.tag_project_documents(user, folder)
        return {"name": folder, "memory": _policy_dict(policy),
                "documents_private": policy.documents_private, "description": policy.description,
                "memories_filed": tagged_memories, "documents_filed": tagged_documents}

    def _tag_project_memories(user, folder) -> int:
        chat_ids = _project_chat_ids(user, folder)
        if not chat_ids:
            return 0
        try:
            entries = memory_manager.load_all_for_update()
        except MemoryStoreUnreadable as error:
            logger.error("Memory store unreadable; project %s memories not filed: %s", folder, error)
            return 0
        changed = folder_memory.tag_chat_memories(
            [e for e in entries if not user or e.get("owner") == user], chat_ids, folder)
        if changed:
            memory_manager.save(entries)
        return changed

    @router.put("/{name}/settings")
    def set_folder_settings(request: Request, name: str, body: dict):
        return _save_settings(request, name, body)

    @router.put("/{name}/memory")
    def set_folder_memory(request: Request, name: str, body: dict):
        return _save_settings(request, name, body)

    @router.post("/{name}/rename")
    def rename_folder(request: Request, name: str, body: dict):
        """Rename a project: its chats, its memory settings and its private memories."""
        user = effective_user(request)
        old, new = name.strip(), str(body.get("new_name") or "").strip()
        if not old or not new:
            raise HTTPException(400, "Both the current and the new project name are required")
        if old == new:
            return {"name": new, "chats": 0, "memories": 0}
        db = SessionLocal()
        try:
            query = db.query(DbSession).filter(DbSession.folder == old)
            if user:
                query = query.filter(DbSession.owner == user)
            rows = query.all()
            for row in rows:
                row.folder = new
            db.commit()
            moved_chats = len(rows)
        finally:
            db.close()
        folder_memory.rename_policy(user, old, new)
        moved_documents = folder_documents.rename_project_documents(user, old, new)
        moved_memories = 0
        try:
            entries = memory_manager.load_all_for_update()
        except MemoryStoreUnreadable as error:
            logger.error("Memory store unreadable; project %s renamed without its memories: %s", old, error)
            entries = None
        if entries is not None:
            for entry in entries:
                if (not user or entry.get("owner") == user) and str(entry.get("folder") or "").strip() == old:
                    entry["folder"] = new
                    moved_memories += 1
            if moved_memories:
                memory_manager.save(entries)
        return {"name": new, "chats": moved_chats, "memories": moved_memories, "documents": moved_documents}

    @router.get("/{name}/home")
    def project_home(request: Request, name: str):
        """A project's page: its chats, the memories made in it and its files."""
        from core.database import Document
        user = effective_user(request)
        folder = name.strip()
        policy = folder_memory.get_policy(user, folder)
        db = SessionLocal()
        try:
            query = db.query(DbSession).filter(DbSession.folder == folder, DbSession.archived == False)  # noqa: E712
            if user:
                query = query.filter(DbSession.owner == user)
            chats = query.all()
            chat_ids = {c.id for c in chats}
            # Like the sidebar: a chat with no messages and no document yet
            # isn't listed (it's still being started).
            with_docs = {r[0] for r in db.query(Document.session_id).filter(Document.session_id.in_(sorted(chat_ids)))} if chat_ids else set()
            listed = [c for c in chats if (c.message_count or 0) > 0 or c.id in with_docs]
            chat_rows = sorted((
                {"id": c.id, "name": c.name or "Untitled chat",
                 "last_active": (c.last_message_at or c.updated_at or c.created_at).isoformat()
                 if (c.last_message_at or c.updated_at or c.created_at) else None}
                for c in listed), key=lambda c: c["last_active"] or "", reverse=True)
            docs = db.query(Document).filter(Document.archived == False)  # noqa: E712
            if user:
                docs = docs.filter(Document.owner == user)
            from sqlalchemy import or_
            conditions = [Document.folder == folder]
            if chat_ids:
                conditions.append(Document.session_id.in_(sorted(chat_ids)))
            doc_rows = [
                {"id": d.id, "title": d.title or "Untitled", "language": d.language,
                 "updated_at": d.updated_at.isoformat() if d.updated_at else None,
                 "private": (d.folder or "") == folder}
                for d in docs.filter(or_(*conditions)).order_by(Document.updated_at.desc()).limit(200).all()
            ]
        finally:
            db.close()
        memories = [
            {"id": e.get("id"), "text": e.get("text") or "", "category": e.get("category"),
             "timestamp": e.get("timestamp"), "private": str(e.get("folder") or "").strip() == folder}
            for e in memory_manager.load(user)
            if str(e.get("folder") or "").strip() == folder or str(e.get("session_id") or "") in chat_ids
        ]
        memories.sort(key=lambda m: m.get("timestamp") or 0, reverse=True)
        return {
            "name": folder, "description": policy.description,
            "memory": _policy_dict(policy), "documents_private": policy.documents_private,
            "chats": chat_rows, "memories": memories, "documents": doc_rows,
        }

    @router.get("/{name}/chat-ids")
    def project_chat_ids(request: Request, name: str):
        """Every chat in the project, so the browser can delete them one by one
        through the normal chat-delete path."""
        return {"name": name.strip(), "chat_ids": sorted(_project_chat_ids(effective_user(request), name.strip()))}

    @router.delete("/{name}")
    def delete_folder(request: Request, name: str, mode: str = "move"):
        """Delete a project.

        ``mode=move``: its chats move to Main and its private memories and
        documents join the shared pool. ``mode=everything``: its private
        memories and documents are deleted (the browser deletes its chats
        first, through the chat-delete path; any left are moved to Main).
        """
        user = effective_user(request)
        folder = name.strip()
        if not folder:
            raise HTTPException(400, "A project name is required")
        if mode not in ("move", "everything"):
            raise HTTPException(400, "mode must be 'move' or 'everything'")
        from core.database import Document
        db = SessionLocal()
        try:
            chats = db.query(DbSession).filter(DbSession.folder == folder)
            if user:
                chats = chats.filter(DbSession.owner == user)
            moved_chats = 0
            for row in chats.all():
                row.folder = None
                moved_chats += 1
            docs = db.query(Document).filter(Document.folder == folder)
            if user:
                docs = docs.filter(Document.owner == user)
            documents = 0
            for doc in docs.all():
                documents += 1
                if mode == "everything":
                    db.delete(doc)
                else:
                    doc.folder = None
            db.commit()
        finally:
            db.close()
        memories = 0
        try:
            entries = memory_manager.load_all_for_update()
        except MemoryStoreUnreadable as error:
            logger.error("Memory store unreadable; project %s deleted without its memories: %s", folder, error)
            entries = None
        removed_ids = []
        if entries is not None:
            kept = []
            for entry in entries:
                mine = (not user or entry.get("owner") == user) and str(entry.get("folder") or "").strip() == folder
                if not mine:
                    kept.append(entry)
                    continue
                memories += 1
                if mode == "move":
                    entry.pop("folder", None)
                    kept.append(entry)
                else:
                    removed_ids.append(entry.get("id"))
            if memories:
                memory_manager.save(kept)
        # Deleted memories leave the search index too.
        if memory_vector is not None and getattr(memory_vector, "healthy", False):
            for memory_id in removed_ids:
                try:
                    memory_vector.remove(memory_id)
                except Exception as error:
                    logger.warning("Could not remove memory %s from the index: %s", memory_id, error)
        folder_memory.delete_policy(user, folder)
        return {"name": folder, "mode": mode, "chats_moved": moved_chats,
                "memories": memories, "documents": documents}

    @router.get("/move-impact")
    def move_impact(request: Request, session_id: str, to: str = ""):
        """How many of a chat's memories a move would change; 0 means don't ask."""
        user = effective_user(request)
        current = _session_folder(user, session_id)
        count = folder_memory.move_needs_choice(memory_manager.load(user), user, session_id, current, to or None)
        documents = folder_documents.documents_needing_move_choice(user, session_id, current, to or None)
        return {"session_id": session_id, "from": current, "to": (to or "").strip() or None,
                "memories": count, "documents": documents}

    return router
