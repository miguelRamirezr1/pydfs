import os
import sqlite3

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
        """)
