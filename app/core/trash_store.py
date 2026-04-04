"""
app/core/trash_store.py
════════════════════════════════════════════════════════════════════════════════
Persistent, thread-safe soft-delete registry.

GUARANTEES
──────────
• Atomic writes  — the file is written to a temp path then renamed, so a
  crash mid-write never produces a corrupt file.
• Thread-safe    — an asyncio.Lock serialises all mutations.
• Fast reads     — the entire store is held in memory after the first load;
  disk I/O only on mutation.
• Zero external deps — stdlib only (json, pathlib, asyncio, os).
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ── Configuration ─────────────────────────────────────────────────────────────
_STORE_PATH = Path(os.getenv("TRASH_STORE_PATH", "data/trash_store.json"))

# ── In-memory state ───────────────────────────────────────────────────────────
_lock: asyncio.Lock | None = None
_items: list[dict[str, Any]] = []
_loaded: bool = False


def _get_lock() -> asyncio.Lock:
    """Lazy-init the lock inside the running event loop."""
    global _lock
    if _lock is None:
        _lock = asyncio.Lock()
    return _lock


# ── Persistence helpers ───────────────────────────────────────────────────────

def _load_from_disk() -> None:
    """Read the JSON file into _items. Called once, synchronously, before the
    first async operation so we don't need an await at call-site."""
    global _items, _loaded
    if _loaded:
        return
    if _STORE_PATH.exists():
        try:
            data = json.loads(_STORE_PATH.read_text(encoding="utf-8"))
            _items = data.get("items", [])
        except (json.JSONDecodeError, OSError) as exc:
            logger.error("trash_store: failed to load %s — %s", _STORE_PATH, exc)
            _items = []
    else:
        _items = []
    _loaded = True


def _save_to_disk() -> None:
    """Atomic write: temp file → rename."""
    _STORE_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps({"items": _items}, ensure_ascii=False, default=str, indent=2)
    fd, tmp = tempfile.mkstemp(dir=_STORE_PATH.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(payload)
        os.replace(tmp, _STORE_PATH)
    except OSError:
        with contextlib.suppress(OSError):
            os.unlink(tmp)
        raise


# ── Public API ────────────────────────────────────────────────────────────────

async def add(
    record_id: str,
    module: str,         # "fiverr" | "upwork"
    record_type: str,    # "profile" | "snapshot" | "order"
    snapshot: dict[str, Any],
) -> dict[str, Any]:
    """
    Soft-delete a record.

    Parameters
    ----------
    record_id   : Original DB primary key.
    module      : Module name ("fiverr" or "upwork").
    record_type : "profile", "snapshot", or "order".
    snapshot    : Full record dict captured at deletion time.

    Returns the trash item dict.
    Idempotent — re-deleting an already-deleted id is a no-op that returns
    the existing trash item.
    """
    _load_from_disk()
    async with _get_lock():
        # Idempotency guard
        existing = next((i for i in _items if i["id"] == record_id), None)
        if existing:
            return existing

        item: dict[str, Any] = {
            "id":        record_id,
            "module":    module,
            "type":      record_type,
            "deletedAt": datetime.now(timezone.utc).isoformat(),
            "snapshot":  snapshot,
        }
        _items.append(item)
        _save_to_disk()
        return item


async def remove(record_id: str) -> bool:
    """
    Restore a soft-deleted record (removes from trash registry).

    Returns True if the item was found and removed, False otherwise.
    """
    global _items
    _load_from_disk()
    async with _get_lock():
        before = len(_items)
        _items = [i for i in _items if i["id"] != record_id]
        if len(_items) < before:
            _save_to_disk()
            return True
        return False


async def get_all(
    module: str | None = None,
    record_type: str | None = None,
) -> list[dict[str, Any]]:
    """
    Return all trash items, optionally filtered by module and/or type.
    Results are sorted newest-deleted-first.
    """
    _load_from_disk()
    results = _items
    if module:
        results = [i for i in results if i["module"] == module]
    if record_type:
        results = [i for i in results if i["type"] == record_type]
    return sorted(results, key=lambda x: x["deletedAt"], reverse=True)


async def get_by_id(record_id: str) -> dict[str, Any] | None:
    """Return a single trash item by its original DB id, or None."""
    _load_from_disk()
    return next((i for i in _items if i["id"] == record_id), None)


def is_deleted(record_id: str) -> bool:
    """
    Synchronous membership test — used as a fast filter inside summary
    builders to exclude soft-deleted entries/orders from live calculations.
    Safe to call without await because it never mutates state.
    """
    _load_from_disk()
    return any(i["id"] == record_id for i in _items)


# ── Missing import fix ────────────────────────────────────────────────────────
import contextlib  # noqa: E402  (stdlib, safe to import after functions)