"""Chat folders and their memory policies (see src/folder_memory.py)."""
import logging

from fastapi import APIRouter, HTTPException, Request

from core.database import Session as DbSession, SessionLocal
from src import folder_memory
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


def setup_folder_routes(memory_manager: MemoryManager):
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
        names = sorted(set(counts) | set(policies), key=str.casefold)
        return {"folders": [
            {
                "name": name,
                "chats": counts.get(name, 0),
                "private_memories": private.get(name, 0),
                "memory": {
                    "receive": policies.get(name, folder_memory.DEFAULT_POLICY).receive,
                    "share": policies.get(name, folder_memory.DEFAULT_POLICY).share,
                    "created_at": policies.get(name, folder_memory.DEFAULT_POLICY).created_at,
                    "snapshot_at": policies.get(name, folder_memory.DEFAULT_POLICY).snapshot_at,
                },
            }
            for name in names
        ]}

    @router.put("/{name}/memory")
    def set_folder_memory(request: Request, name: str, body: dict):
        user = effective_user(request)
        try:
            policy = folder_memory.set_policy(
                user, name, receive=str(body.get("receive") or "all"), share=body.get("share") is not False)
        except ValueError as error:
            raise HTTPException(400, str(error))
        return {"name": name.strip(), "memory": {
            "receive": policy.receive, "share": policy.share,
            "created_at": policy.created_at, "snapshot_at": policy.snapshot_at}}

    @router.get("/move-impact")
    def move_impact(request: Request, session_id: str, to: str = ""):
        """How many of a chat's memories a move would change; 0 means don't ask."""
        user = effective_user(request)
        current = _session_folder(user, session_id)
        count = folder_memory.move_needs_choice(memory_manager.load(user), user, session_id, current, to or None)
        return {"session_id": session_id, "from": current, "to": (to or "").strip() or None, "memories": count}

    return router
