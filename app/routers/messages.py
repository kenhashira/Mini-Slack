import sqlite3

from fastapi import APIRouter, Depends, Query, Response

from app.db import get_db
from app.deps import current_user
from app.errors import forbidden, not_found
from app.routers.channels import get_channel_or_404, require_channel_writable
from app.schemas import MessageCreate, MessageEdit

router = APIRouter(tags=["messages"])

# reply_count is computed per message; replies themselves have a parent_id.
MESSAGE_SELECT = """
    SELECT m.*,
           (SELECT COUNT(*) FROM messages r WHERE r.parent_id = m.id) AS reply_count
    FROM messages m
"""


def message_dict(row: sqlite3.Row) -> dict:
    return {
        "id": row["id"],
        "channel_id": row["channel_id"],
        "user_id": row["user_id"],
        "parent_id": row["parent_id"],
        "body": row["body"],
        "created_at": row["created_at"],
        "edited_at": row["edited_at"],
        "reply_count": row["reply_count"],
    }


def get_message_or_404(conn: sqlite3.Connection, message_id: int) -> sqlite3.Row:
    row = conn.execute(MESSAGE_SELECT + " WHERE m.id = ?", (message_id,)).fetchone()
    if row is None:
        raise not_found(f"Message {message_id} not found.")
    return row


@router.post("/channels/{channel_id}/messages", status_code=201)
def post_message(
    channel_id: int,
    body: MessageCreate,
    user_id: str = Depends(current_user),
    conn: sqlite3.Connection = Depends(get_db),
):
    require_channel_writable(conn, channel_id)
    cur = conn.execute(
        "INSERT INTO messages (channel_id, user_id, body) VALUES (?, ?, ?)",
        (channel_id, user_id, body.body),
    )
    conn.commit()
    return message_dict(get_message_or_404(conn, cur.lastrowid))


@router.get("/channels/{channel_id}/messages")
def list_messages(
    channel_id: int,
    limit: int = Query(50, ge=1, le=100),
    before: int | None = Query(None, ge=1),
    user_id: str = Depends(current_user),
    conn: sqlite3.Connection = Depends(get_db),
):
    """Top-level messages, newest first. Pass next_before back as `before` for the next page."""
    get_channel_or_404(conn, channel_id)
    sql = MESSAGE_SELECT + " WHERE m.channel_id = ? AND m.parent_id IS NULL"
    params: list = [channel_id]
    if before is not None:
        sql += " AND m.id < ?"
        params.append(before)
    sql += " ORDER BY m.id DESC LIMIT ?"
    params.append(limit + 1)  # one extra row tells us whether another page exists
    rows = conn.execute(sql, params).fetchall()
    has_more = len(rows) > limit
    rows = rows[:limit]
    return {
        "messages": [message_dict(r) for r in rows],
        "next_before": rows[-1]["id"] if has_more else None,
    }


@router.patch("/messages/{message_id}")
def edit_message(
    message_id: int,
    body: MessageEdit,
    user_id: str = Depends(current_user),
    conn: sqlite3.Connection = Depends(get_db),
):
    message = get_message_or_404(conn, message_id)
    if message["user_id"] != user_id:
        raise forbidden("Only the author can edit this message.")
    require_channel_writable(conn, message["channel_id"])
    conn.execute(
        "UPDATE messages SET body = ?, edited_at = CURRENT_TIMESTAMP WHERE id = ?",
        (body.body, message_id),
    )
    conn.commit()
    return message_dict(get_message_or_404(conn, message_id))


@router.delete("/messages/{message_id}", status_code=204)
def delete_message(
    message_id: int,
    user_id: str = Depends(current_user),
    conn: sqlite3.Connection = Depends(get_db),
):
    message = get_message_or_404(conn, message_id)
    if message["user_id"] != user_id:
        raise forbidden("Only the author can delete this message.")
    require_channel_writable(conn, message["channel_id"])
    conn.execute("DELETE FROM messages WHERE id = ?", (message_id,))  # replies cascade
    conn.commit()
    return Response(status_code=204)
