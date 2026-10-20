"""Per-folder memory scopes.

Every chat folder has a memory policy, chosen when the folder is created and
changeable later. Two independent settings:

* ``receive``: which shared memories chats in the folder can see.
    - ``all``: every shared memory, including ones saved later (default).
    - ``snapshot``: only shared memories that existed when the folder's
      snapshot was taken (``snapshot_at``); later ones never arrive.
    - ``none``: no shared memories at all; a fresh start.
* ``share``: whether memories saved from the folder's chats join the shared
  pool (True, default) or stay private to the folder (False).

The default, ``receive="all", share=True``, is exactly the behaviour before
folders had memory settings, so existing folders and memories are unchanged.

A third setting, ``documents_private``, keeps the folder's documents to itself
the same way; the document rules are in src/folder_documents.py.

A memory carries a ``folder`` field only when it was saved in a folder that
does not share. It belongs to the shared pool when it has no ``folder`` or its
folder shares now. Chats outside any folder see the whole shared pool.
"""
from __future__ import annotations

import time
from dataclasses import asdict, dataclass
from typing import Any, Iterable, Optional

PREFS_KEY = "folder_memory"
RECEIVE_MODES = ("all", "snapshot", "none")


@dataclass(frozen=True)
class FolderMemoryPolicy:
    receive: str = "all"
    share: bool = True
    created_at: int = 0
    snapshot_at: int = 0
    documents_private: bool = False

    @property
    def is_default(self) -> bool:
        return self.receive == "all" and self.share and not self.documents_private


DEFAULT_POLICY = FolderMemoryPolicy()


def _norm_folder(folder: Any) -> str:
    return str(folder or "").strip()


def _load_prefs(owner: Optional[str]) -> dict:
    from routes.prefs_routes import _load_for_user
    return _load_for_user(owner) or {}


def _save_prefs(owner: Optional[str], prefs: dict) -> None:
    from routes.prefs_routes import _save_for_user
    _save_for_user(owner, prefs)


def _policies(prefs: dict) -> dict:
    value = prefs.get(PREFS_KEY)
    return value if isinstance(value, dict) else {}


def _coerce(raw: Any) -> FolderMemoryPolicy:
    if not isinstance(raw, dict):
        return DEFAULT_POLICY
    receive = raw.get("receive") if raw.get("receive") in RECEIVE_MODES else "all"
    share = raw.get("share") is not False
    try:
        created_at = int(raw.get("created_at") or 0)
        snapshot_at = int(raw.get("snapshot_at") or 0)
    except (TypeError, ValueError):
        created_at = snapshot_at = 0
    return FolderMemoryPolicy(receive=receive, share=share, created_at=created_at, snapshot_at=snapshot_at,
                              documents_private=raw.get("documents_private") is True)


def get_policy(owner: Optional[str], folder: Any, *, prefs: Optional[dict] = None) -> FolderMemoryPolicy:
    """The folder's policy; folderless chats and unknown folders use the default."""
    name = _norm_folder(folder)
    if not name:
        return DEFAULT_POLICY
    prefs = _load_prefs(owner) if prefs is None else prefs
    return _coerce(_policies(prefs).get(name))


def all_policies(owner: Optional[str]) -> dict[str, FolderMemoryPolicy]:
    return {name: _coerce(raw) for name, raw in _policies(_load_prefs(owner)).items()}


def set_policy(owner: Optional[str], folder: Any, *, receive: str, share: bool,
               documents_private: Optional[bool] = None,
               now: Optional[int] = None) -> FolderMemoryPolicy:
    """Create or change a folder's policy.

    ``snapshot_at`` is taken when the folder is created with ``snapshot``, or
    when it is switched to ``snapshot`` later; it is kept while the folder
    stays in ``snapshot`` so changing ``share`` doesn't move it.
    ``documents_private`` left as None keeps the folder's current value.
    """
    name = _norm_folder(folder)
    if not name:
        raise ValueError("A folder name is required")
    if receive not in RECEIVE_MODES:
        raise ValueError(f"receive must be one of {RECEIVE_MODES}")
    now = int(time.time()) if now is None else int(now)
    prefs = _load_prefs(owner)
    policies = dict(_policies(prefs))
    previous = _coerce(policies.get(name)) if name in policies else None
    created_at = previous.created_at if previous and previous.created_at else now
    if receive == "snapshot":
        snapshot_at = previous.snapshot_at if previous and previous.receive == "snapshot" and previous.snapshot_at else now
    else:
        snapshot_at = 0
    if documents_private is None:
        documents_private = previous.documents_private if previous else False
    policy = FolderMemoryPolicy(receive=receive, share=bool(share), created_at=created_at, snapshot_at=snapshot_at,
                                documents_private=bool(documents_private))
    policies[name] = asdict(policy)
    prefs[PREFS_KEY] = policies
    _save_prefs(owner, prefs)
    return policy


def rename_policy(owner: Optional[str], old: Any, new: Any) -> None:
    old_name, new_name = _norm_folder(old), _norm_folder(new)
    if not old_name or not new_name or old_name == new_name:
        return
    prefs = _load_prefs(owner)
    policies = dict(_policies(prefs))
    if old_name in policies and new_name not in policies:
        policies[new_name] = policies.pop(old_name)
        prefs[PREFS_KEY] = policies
        _save_prefs(owner, prefs)


def folder_for_new_memory(owner: Optional[str], folder: Any) -> Optional[str]:
    """The ``folder`` tag a memory saved from a chat in ``folder`` should carry."""
    name = _norm_folder(folder)
    if not name:
        return None
    return None if get_policy(owner, name).share else name


def _in_shared_pool(entry: dict, prefs: dict) -> bool:
    tag = _norm_folder(entry.get("folder"))
    return not tag or _coerce(_policies(prefs).get(tag)).share


def memory_visible(entry: dict, owner: Optional[str], folder: Any, *, prefs: Optional[dict] = None) -> bool:
    """Whether a chat in ``folder`` (None for folderless) may see ``entry``."""
    prefs = _load_prefs(owner) if prefs is None else prefs
    name = _norm_folder(folder)
    tag = _norm_folder(entry.get("folder"))
    if name and tag == name:
        return True
    if not _in_shared_pool(entry, prefs):
        return False
    if not name:
        return True
    policy = _coerce(_policies(prefs).get(name))
    if policy.receive == "none":
        return False
    if policy.receive == "snapshot":
        try:
            return int(entry.get("timestamp") or 0) <= policy.snapshot_at
        except (TypeError, ValueError):
            return False
    return True


def filter_visible(entries: Iterable[dict], owner: Optional[str], folder: Any) -> list[dict]:
    prefs = _load_prefs(owner)
    return [e for e in entries if isinstance(e, dict) and memory_visible(e, owner, folder, prefs=prefs)]


def move_needs_choice(entries: Iterable[dict], owner: Optional[str], session_id: str,
                      from_folder: Any, to_folder: Any) -> int:
    """How many of the chat's memories a move would change the visibility of.

    0 means no question is needed: the chat has no memories, or both folders
    put its memories in the same place (for example two sharing folders).
    """
    src, dst = _norm_folder(from_folder), _norm_folder(to_folder)
    if src == dst:
        return 0
    if folder_for_new_memory(owner, src) == folder_for_new_memory(owner, dst):
        return 0
    return sum(1 for e in entries if isinstance(e, dict) and str(e.get("session_id") or "") == str(session_id))


def retag_for_move(entries: list[dict], owner: Optional[str], session_id: str, to_folder: Any) -> int:
    """Re-file the chat's memories under ``to_folder``'s rules. Returns the count changed."""
    tag = folder_for_new_memory(owner, to_folder)
    changed = 0
    for entry in entries:
        if not isinstance(entry, dict) or str(entry.get("session_id") or "") != str(session_id):
            continue
        if _norm_folder(entry.get("folder")) == _norm_folder(tag):
            continue
        if tag:
            entry["folder"] = tag
        else:
            entry.pop("folder", None)
        changed += 1
    return changed


def tag_chat_memories(entries: list[dict], chat_ids: Iterable[str], folder: Any) -> int:
    """File untagged memories saved from ``chat_ids`` under ``folder``. Used
    when a project starts keeping its memories private. Returns the count."""
    name = _norm_folder(folder)
    ids = {str(c) for c in chat_ids}
    if not name or not ids:
        return 0
    changed = 0
    for entry in entries:
        if not isinstance(entry, dict) or _norm_folder(entry.get("folder")):
            continue
        if str(entry.get("session_id") or "") in ids:
            entry["folder"] = name
            changed += 1
    return changed


def session_folder(session_id: Any) -> Optional[str]:
    """The project (folder) a chat is in, from the database; None if none or unknown."""
    sid = str(session_id or "").strip()
    if not sid:
        return None
    try:
        from core.database import Session as DbSession, SessionLocal
    except Exception:
        return None
    db = SessionLocal()
    try:
        row = db.query(DbSession.folder).filter(DbSession.id == sid).first()
        return _norm_folder(row[0]) or None if row else None
    except Exception:
        return None
    finally:
        db.close()


def tag_new_memory(entry: dict, owner: Optional[str], session_id: Any) -> dict:
    """Mark a memory saved from a chat as private to its project when the
    project doesn't share. Leaves shared memories untagged."""
    if not isinstance(entry, dict):
        return entry
    tag = folder_for_new_memory(owner, session_folder(session_id))
    if tag:
        entry["folder"] = tag
    else:
        entry.pop("folder", None)
    return entry
