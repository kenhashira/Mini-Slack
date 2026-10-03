import sqlite3

import pytest

from app.db import connect, init_db


def seed(conn):
    conn.execute("INSERT INTO users (id) VALUES ('alice'), ('bob')")
    conn.execute("INSERT INTO channels (name, created_by) VALUES ('general', 'alice')")
    conn.execute(
        "INSERT INTO messages (channel_id, user_id, body) VALUES (1, 'alice', 'hello')"
    )
    conn.commit()


def test_all_tables_exist(conn):
    names = {
        r["name"]
        for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
    }
    assert {"users", "channels", "messages", "reactions", "read_markers"} <= names


def test_init_db_is_idempotent(db_path, conn):
    seed(conn)
    init_db(db_path)  # running again must not wipe or fail
    assert conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0] == 1


def test_channel_names_are_unique_ignoring_case(conn):
    seed(conn)
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO channels (name, created_by) VALUES ('GENERAL', 'bob')")


def test_foreign_keys_are_enforced(conn):
    seed(conn)
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO messages (channel_id, user_id, body) VALUES (999, 'alice', 'x')"
        )


def test_reaction_is_unique_per_user_per_emoji(conn):
    seed(conn)
    conn.execute("INSERT INTO reactions (message_id, user_id, emoji) VALUES (1, 'bob', ':+1:')")
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO reactions (message_id, user_id, emoji) VALUES (1, 'bob', ':+1:')"
        )
    # A different emoji, or a different user, is fine.
    conn.execute("INSERT INTO reactions (message_id, user_id, emoji) VALUES (1, 'bob', ':tada:')")
    conn.execute("INSERT INTO reactions (message_id, user_id, emoji) VALUES (1, 'alice', ':+1:')")


def test_deleting_a_message_cascades_to_replies_and_reactions(conn):
    seed(conn)
    conn.execute(
        "INSERT INTO messages (channel_id, user_id, parent_id, body) VALUES (1, 'bob', 1, 'reply')"
    )
    conn.execute("INSERT INTO reactions (message_id, user_id, emoji) VALUES (2, 'alice', ':+1:')")
    conn.commit()
    conn.execute("DELETE FROM messages WHERE id = 1")
    conn.commit()
    assert conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM reactions").fetchone()[0] == 0


def test_read_marker_is_unique_per_user_and_channel(conn):
    seed(conn)
    conn.execute("INSERT INTO read_markers (user_id, channel_id) VALUES ('bob', 1)")
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO read_markers (user_id, channel_id) VALUES ('bob', 1)")
