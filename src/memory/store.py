"""Encrypted per-driver conversation memory backed by SQLite.

Each driver's memory is AES-256-GCM encrypted with a key derived from
the master secret + driver_id. Even with DB access, cross-driver data
is cryptographically isolated.

Memory auto-expires after the configured TTL (default 14 hours).
Expired rows are hard-deleted on every read — not just filtered.
"""

import json
import logging
import os
import sqlite3
import time
from datetime import datetime, timezone
from typing import Optional

import yaml

from src.memory.crypto import encrypt, decrypt

logger = logging.getLogger(__name__)

_DB_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "data", "memory.db")
_CONFIG_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "config", "betty.yaml")


def _get_ttl_seconds() -> int:
    """Read memory_duration_hours from config, default 14."""
    try:
        with open(_CONFIG_PATH, "r") as f:
            config = yaml.safe_load(f)
        hours = config.get("betty", {}).get("memory", {}).get("memory_duration_hours", 14)
        return int(hours * 3600)
    except Exception:
        return 14 * 3600


def _get_db() -> sqlite3.Connection:
    """Get a SQLite connection, creating the table if needed."""
    os.makedirs(os.path.dirname(_DB_PATH), exist_ok=True)
    conn = sqlite3.connect(_DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS driver_memory (
            driver_id TEXT PRIMARY KEY,
            encrypted_blob BLOB NOT NULL,
            updated_at REAL NOT NULL
        )
    """)
    conn.commit()
    return conn


def _purge_expired(conn: sqlite3.Connection, ttl: int) -> int:
    """Hard-delete expired rows. Returns count deleted."""
    cutoff = time.time() - ttl
    cursor = conn.execute(
        "DELETE FROM driver_memory WHERE updated_at < ?", (cutoff,)
    )
    conn.commit()
    deleted = cursor.rowcount
    if deleted:
        logger.info("Purged %d expired memory entries", deleted)
    return deleted


def _serialize(entries: list[dict]) -> bytes:
    return json.dumps(entries, ensure_ascii=False).encode("utf-8")


def _deserialize(data: bytes) -> list[dict]:
    return json.loads(data.decode("utf-8"))


# --- Public API ---

def get_memory(driver_id: str) -> list[dict]:
    """Retrieve decrypted conversation memory for a driver.

    Returns a list of conversation entries, or [] if no memory / expired / wrong key.
    Purges expired entries on every call.
    """
    ttl = _get_ttl_seconds()
    conn = _get_db()
    try:
        _purge_expired(conn, ttl)

        row = conn.execute(
            "SELECT encrypted_blob, updated_at FROM driver_memory WHERE driver_id = ?",
            (driver_id,),
        ).fetchone()

        if not row:
            return []

        encrypted_blob, updated_at = row

        # Double-check TTL (shouldn't be needed after purge, but defence in depth)
        if time.time() - updated_at > ttl:
            conn.execute("DELETE FROM driver_memory WHERE driver_id = ?", (driver_id,))
            conn.commit()
            return []

        plaintext = decrypt(driver_id, encrypted_blob)
        entries = _deserialize(plaintext)
        logger.debug("Loaded %d memory entries for %s", len(entries), driver_id)
        return entries

    except Exception:
        logger.exception("Failed to read memory for %s", driver_id)
        return []
    finally:
        conn.close()


def add_entry(
    driver_id: str,
    summary: str,
    fatigue_assessment: str,
    action_taken: str,
    topics: Optional[list[str]] = None,
) -> None:
    """Add a conversation entry to a driver's memory.

    Appends to existing entries (up to 10 max, oldest dropped).
    Encrypts and stores the full list.
    """
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "summary": summary,
        "fatigue_assessment": fatigue_assessment,
        "action_taken": action_taken,
        "topics": topics or [],
    }

    # Load existing entries
    existing = get_memory(driver_id)
    existing.append(entry)

    # Keep last 10 entries max
    if len(existing) > 10:
        existing = existing[-10:]

    # Encrypt and store
    plaintext = _serialize(existing)
    encrypted = encrypt(driver_id, plaintext)

    conn = _get_db()
    try:
        conn.execute(
            """INSERT INTO driver_memory (driver_id, encrypted_blob, updated_at)
               VALUES (?, ?, ?)
               ON CONFLICT(driver_id) DO UPDATE SET
                 encrypted_blob = excluded.encrypted_blob,
                 updated_at = excluded.updated_at""",
            (driver_id, encrypted, time.time()),
        )
        conn.commit()
        logger.info("Saved memory for %s (%d entries)", driver_id, len(existing))
    except Exception:
        logger.exception("Failed to save memory for %s", driver_id)
    finally:
        conn.close()


def get_memory_summary(driver_id: str) -> Optional[str]:
    """Format driver memory as a natural-language summary for prompt injection.

    Returns None if no memory exists.
    """
    entries = get_memory(driver_id)
    if not entries:
        return None

    lines = []
    for e in entries:
        ts = e.get("timestamp", "")
        # Parse and format relative time
        try:
            dt = datetime.fromisoformat(ts)
            ago = datetime.now(timezone.utc) - dt
            hours = ago.total_seconds() / 3600
            if hours < 1:
                time_str = f"{int(ago.total_seconds() / 60)} min ago"
            else:
                time_str = f"{hours:.1f}h ago"
        except Exception:
            time_str = ts

        summary = e.get("summary", "")
        fatigue = e.get("fatigue_assessment", "")
        action = e.get("action_taken", "")
        topics = e.get("topics", [])

        line = f"- {time_str}: {summary}"
        if fatigue:
            line += f" (fatigue: {fatigue})"
        if action and action != "none":
            line += f" (action: {action})"
        lines.append(line)

    # Add topic summary across all entries
    all_topics = []
    for e in entries:
        all_topics.extend(e.get("topics", []))
    if all_topics:
        unique_topics = list(dict.fromkeys(all_topics))  # preserve order, dedupe
        lines.append(f"- Topics discussed: {', '.join(unique_topics)}")

    return "\n".join(lines)


def clear_memory(driver_id: str) -> None:
    """Delete a driver's memory (for testing or privacy requests)."""
    conn = _get_db()
    try:
        conn.execute("DELETE FROM driver_memory WHERE driver_id = ?", (driver_id,))
        conn.commit()
        logger.info("Cleared memory for %s", driver_id)
    except Exception:
        logger.exception("Failed to clear memory for %s", driver_id)
    finally:
        conn.close()


def clear_all() -> None:
    """Delete all memory (for testing)."""
    conn = _get_db()
    try:
        conn.execute("DELETE FROM driver_memory")
        conn.commit()
        logger.info("Cleared all driver memory")
    except Exception:
        logger.exception("Failed to clear all memory")
    finally:
        conn.close()
