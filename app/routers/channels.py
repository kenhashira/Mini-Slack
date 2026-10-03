import sqlite3

from fastapi import APIRouter, Depends

from app.db import get_db
from app.deps import current_user
from app.errors import AppError, conflict, not_found
from app.schemas import ChannelCreate, MarkRead

router = APIRouter(prefix="/channels", tags=["channels"])


def channel_dict(row: sqlite3.Row) -> dict:
    return {
        "id": row["id"],
        "name": row["name"],
        "created_by": row["created_by"],
        "created_at": row["created_at"],
        "archived": row["archived_at"] is not None,
        "archived_at": row["archived_at"],
    }


def get_channel_or_404(conn: sqlite3.Connection, channel_id: int) -> sqlite3.Row:
    row = conn.execute("SELECT * FROM channels WHERE id = ?", (channel_id,)).fetchone()
    if row is None:
        raise not_found(f"Channel {channel_id} not found.")
    return row


def require_channel_writable(conn: sqlite3.Connection, channel_id: int) -> sqlite3.Row:
    """Archived channels are read-only: every write (post, edit, delete, reply,
    react) must call this first. Returns the channel row if writes are allowed."""
    channel = get_channel_or_404(conn, channel_id)
    if channel["archived_at"] is not None:
        raise conflict(f"Channel {channel_id} is archived and read-only.")
    return channel


@router.post("", status_code=201)
def create_channel(
    body: ChannelCreate,
    user_id: str = Depends(current_user),
    conn: sqlite3.Connection = Depends(get_db),
):
    try:
        cur = conn.execute(
            "INSERT INTO channels (name, created_by) VALUES (?, ?)", (body.name, user_id)
        )
        conn.commit()
    except sqlite3.IntegrityError:
        raise conflict(f"A channel named '{body.name}' already exists.")
    return channel_dict(get_channel_or_404(conn, cur.lastrowid))


@router.get("")
def list_channels(
    include_archived: bool = False,
    user_id: str = Depends(current_user),
    conn: sqlite3.Connection = Depends(get_db),
):
    # Unread = top-level messages from other people, newer than this user's read marker.
    # No marker row (channel never opened) counts as marker 0, i.e. everything is unread.
    sql = """
        SELECT c.*,
               (SELECT COUNT(*) FROM messages m
                WHERE m.channel_id = c.id AND m.parent_id IS NULL
                  AND m.user_id != :user
                  AND m.id > COALESCE((SELECT last_read_message_id FROM read_markers rm
                                       WHERE rm.user_id = :user AND rm.channel_id = c.id), 0)
               ) AS unread_count
        FROM channels c
    """
    if not include_archived:
        sql += " WHERE c.archived_at IS NULL"
    rows = conn.execute(sql + " ORDER BY c.name", {"user": user_id}).fetchall()
    return {"channels": [{**channel_dict(r), "unread_count": r["unread_count"]} for r in rows]}


def unread_count(conn: sqlite3.Connection, channel_id: int, user_id: str) -> int:
    return conn.execute(
        """SELECT COUNT(*) FROM messages m
           WHERE m.channel_id = :channel AND m.parent_id IS NULL AND m.user_id != :user
             AND m.id > COALESCE((SELECT last_read_message_id FROM read_markers
                                  WHERE user_id = :user AND channel_id = :channel), 0)""",
        {"channel": channel_id, "user": user_id},
    ).fetchone()[0]


@router.post("/{channel_id}/read")
def mark_read(
    channel_id: int,
    body: MarkRead | None = None,
    user_id: str = Depends(current_user),
    conn: sqlite3.Connection = Depends(get_db),
):
    """Move the caller's read marker forward to `message_id` (default: newest top-level
    message). It never moves backward. Allowed in archived channels: not a content change."""
    get_channel_or_404(conn, channel_id)
    message_id = body.message_id if body else None
    if message_id is None:
        message_id = conn.execute(
            "SELECT COALESCE(MAX(id), 0) FROM messages WHERE channel_id = ? AND parent_id IS NULL",
            (channel_id,),
        ).fetchone()[0]
    else:
        msg = conn.execute(
            "SELECT channel_id, parent_id FROM messages WHERE id = ?", (message_id,)
        ).fetchone()
        if msg is None:
            raise not_found(f"Message {message_id} not found.")
        if msg["channel_id"] != channel_id:
            raise AppError(422, "validation_error", f"Message {message_id} is not in channel {channel_id}.")
        if msg["parent_id"] is not None:
            raise AppError(422, "validation_error", "Mark a top-level message as read, not a reply.")
    # MAX() makes the marker forward-only. The stored number has no foreign key to
    # messages, so deleting the message it points at leaves the marker intact.
    conn.execute(
        """INSERT INTO read_markers (user_id, channel_id, last_read_message_id)
           VALUES (?, ?, ?)
           ON CONFLICT (user_id, channel_id) DO UPDATE SET
               last_read_message_id = MAX(last_read_message_id, excluded.last_read_message_id)""",
        (user_id, channel_id, message_id),
    )
    conn.commit()
    marker = conn.execute(
        "SELECT last_read_message_id FROM read_markers WHERE user_id = ? AND channel_id = ?",
        (user_id, channel_id),
    ).fetchone()[0]
    return {
        "channel_id": channel_id,
        "last_read_message_id": marker,
        "unread_count": unread_count(conn, channel_id, user_id),
    }


@router.post("/{channel_id}/archive")
def archive_channel(
    channel_id: int,
    user_id: str = Depends(current_user),
    conn: sqlite3.Connection = Depends(get_db),
):
    channel = get_channel_or_404(conn, channel_id)
    if channel["archived_at"] is not None:
        raise conflict(f"Channel {channel_id} is already archived.")
    conn.execute(
        "UPDATE channels SET archived_at = CURRENT_TIMESTAMP WHERE id = ?", (channel_id,)
    )
    conn.commit()
    return channel_dict(get_channel_or_404(conn, channel_id))
