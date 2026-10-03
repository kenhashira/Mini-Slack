"""SQLite access: schema, connections, and the per-request connection dependency."""
import os
import sqlite3
from typing import Iterator

from fastapi import Request

DEFAULT_DB_PATH = "mini_slack.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id          TEXT PRIMARY KEY,
    created_at  TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS channels (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL UNIQUE COLLATE NOCASE,
    created_by  TEXT NOT NULL REFERENCES users(id),
    created_at  TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    archived_at TEXT
);

-- A reply is a message whose parent_id points at a top-level message.
CREATE TABLE IF NOT EXISTS messages (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    channel_id  INTEGER NOT NULL REFERENCES channels(id) ON DELETE CASCADE,
    user_id     TEXT NOT NULL REFERENCES users(id),
    parent_id   INTEGER REFERENCES messages(id) ON DELETE CASCADE,
    body        TEXT NOT NULL,
    created_at  TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    edited_at   TEXT
);
CREATE INDEX IF NOT EXISTS idx_messages_channel ON messages(channel_id, id);
CREATE INDEX IF NOT EXISTS idx_messages_parent ON messages(parent_id);

-- The primary key enforces "one reaction per user per emoji per message".
CREATE TABLE IF NOT EXISTS reactions (
    message_id  INTEGER NOT NULL REFERENCES messages(id) ON DELETE CASCADE,
    user_id     TEXT NOT NULL REFERENCES users(id),
    emoji       TEXT NOT NULL,
    created_at  TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (message_id, user_id, emoji)
);

-- Per-user, per-channel "read up to here" marker used for unread counts.
CREATE TABLE IF NOT EXISTS read_markers (
    user_id              TEXT NOT NULL REFERENCES users(id),
    channel_id           INTEGER NOT NULL REFERENCES channels(id) ON DELETE CASCADE,
    last_read_message_id INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (user_id, channel_id)
);
"""


def resolve_db_path(db_path: str | None = None) -> str:
    return db_path or os.environ.get("MINI_SLACK_DB") or DEFAULT_DB_PATH


def connect(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    # SQLite does not enforce foreign keys unless asked, per connection.
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(db_path: str) -> None:
    conn = connect(db_path)
    try:
        conn.executescript(SCHEMA)
        conn.commit()
    finally:
        conn.close()


def get_db(request: Request) -> Iterator[sqlite3.Connection]:
    """FastAPI dependency: one connection per request, always closed."""
    conn = connect(request.app.state.db_path)
    try:
        yield conn
    finally:
        conn.close()
