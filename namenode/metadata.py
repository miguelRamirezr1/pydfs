import os
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Optional

DB_PATH = os.getenv("DB_PATH", "/app/data/metadata.db")


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    with get_conn() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                username      TEXT PRIMARY KEY,
                password_hash TEXT NOT NULL,
                created_at    TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS files (
                file_id    TEXT PRIMARY KEY,
                owner      TEXT NOT NULL,
                path       TEXT NOT NULL,
                size       INTEGER NOT NULL,
                is_dir     INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS blocks (
                block_id   TEXT NOT NULL,
                file_id    TEXT NOT NULL,
                seq        INTEGER NOT NULL,
                datanode   TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS datanodes (
                node_id        TEXT PRIMARY KEY,
                host           TEXT NOT NULL,
                port           INTEGER NOT NULL,
                last_heartbeat TEXT NOT NULL,
                free_bytes     INTEGER NOT NULL
            );

            CREATE UNIQUE INDEX IF NOT EXISTS idx_files_owner_path
                ON files(owner, path);
        """)


#Users

def create_user(username: str, password_hash: str) -> bool:
    """Returns False if username already exists."""
    try:
        with get_conn() as conn:
            conn.execute(
                "INSERT INTO users (username, password_hash, created_at) VALUES (?, ?, ?)",
                (username, password_hash, datetime.now(timezone.utc).isoformat()),
            )
        return True
    except sqlite3.IntegrityError:
        return False


def get_user(username: str) -> Optional[sqlite3.Row]:
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM users WHERE username = ?", (username,)
        ).fetchone()


# ── DataNodes ─────────────────────────────────────────────────────────────────

def get_active_datanodes(timeout_s: float) -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT * FROM datanodes
               WHERE (julianday('now') - julianday(last_heartbeat)) * 86400 < ?
               ORDER BY node_id""",
            (timeout_s,),
        ).fetchall()
        return [dict(r) for r in rows]


# ── Files ─────────────────────────────────────────────────────────────────────

def create_file(file_id: str, owner: str, path: str, size: int) -> bool:
    """Returns False if file_id or (owner, path) already exists."""
    try:
        with get_conn() as conn:
            conn.execute(
                "INSERT INTO files (file_id, owner, path, size, is_dir, created_at) VALUES (?, ?, ?, ?, 0, ?)",
                (file_id, owner, path, size, datetime.now(timezone.utc).isoformat()),
            )
        return True
    except sqlite3.IntegrityError:
        return False


def create_block(block_id: str, file_id: str, seq: int, datanode: str) -> None:
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO blocks (block_id, file_id, seq, datanode) VALUES (?, ?, ?, ?)",
            (block_id, file_id, seq, datanode),
        )


# ── Dirs ──────────────────────────────────────────────────────────────────────

def create_dir(owner: str, path: str) -> bool:
    """Returns False if path already exists for this owner."""
    try:
        with get_conn() as conn:
            conn.execute(
                "INSERT INTO files (file_id, owner, path, size, is_dir, created_at) VALUES (?, ?, ?, 0, 1, ?)",
                (str(uuid.uuid4()), owner, path, datetime.now(timezone.utc).isoformat()),
            )
        return True
    except sqlite3.IntegrityError:
        return False


def delete_dir(owner: str, path: str) -> str:
    """Delete a logical directory. Returns 'ok', 'not_found', or 'not_empty'."""
    with get_conn() as conn:
        row = conn.execute(
            "SELECT file_id FROM files WHERE owner = ? AND path = ? AND is_dir = 1",
            (owner, path),
        ).fetchone()
        if not row:
            return "not_found"
        prefix = path.rstrip("/") + "/"
        children = conn.execute(
            "SELECT 1 FROM files WHERE owner = ? AND path LIKE ? LIMIT 1",
            (owner, prefix + "%"),
        ).fetchone()
        if children:
            return "not_empty"
        conn.execute("DELETE FROM files WHERE file_id = ?", (row["file_id"],))
        return "ok"


# ── Files ─────────────────────────────────────────────────────────────────────

def get_file(owner: str, path: str) -> Optional[sqlite3.Row]:
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM files WHERE owner = ? AND path = ?", (owner, path)
        ).fetchone()


def get_file_blocks(file_id: str) -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT block_id, seq, datanode FROM blocks WHERE file_id = ? ORDER BY seq",
            (file_id,),
        ).fetchall()
        return [dict(r) for r in rows]


def delete_file(owner: str, path: str) -> Optional[list[dict]]:
    """Delete file and blocks from SQLite. Returns list of {block_id, host, port} or None if not found."""
    with get_conn() as conn:
        row = conn.execute(
            "SELECT file_id FROM files WHERE owner = ? AND path = ?", (owner, path)
        ).fetchone()
        if not row:
            return None
        file_id = row["file_id"]
        blocks = conn.execute(
            """SELECT b.block_id, d.host, d.port
               FROM blocks b
               JOIN datanodes d ON d.node_id = b.datanode
               WHERE b.file_id = ?""",
            (file_id,),
        ).fetchall()
        conn.execute("DELETE FROM blocks WHERE file_id = ?", (file_id,))
        conn.execute("DELETE FROM files WHERE file_id = ?", (file_id,))
        return [dict(b) for b in blocks]


def list_files(owner: str, directory: Optional[str] = None) -> list[dict]:
    with get_conn() as conn:
        if directory:
            prefix = directory.strip("/") + "/"
            rows = conn.execute(
                "SELECT * FROM files WHERE owner = ? AND path LIKE ?",
                (owner, prefix + "%"),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM files WHERE owner = ?", (owner,)
            ).fetchall()
        return [dict(r) for r in rows]
