import sqlite3
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response

from app.db import get_db
from app.deps import current_user
from app.errors import conflict, not_found
from app.routers.channels import require_channel_writable
from app.routers.messages import get_message_or_404, serialize_message
from app.schemas import Emoji, ReactionCreate

router = APIRouter(tags=["reactions"])


@router.post("/messages/{message_id}/reactions", status_code=201)
def add_reaction(
    message_id: int,
    body: ReactionCreate,
    user_id: str = Depends(current_user),
    conn: sqlite3.Connection = Depends(get_db),
):
    message = get_message_or_404(conn, message_id)
    require_channel_writable(conn, message["channel_id"])
    try:
        # The primary key (message, user, emoji) is what enforces one reaction per user per emoji.
        conn.execute(
            "INSERT INTO reactions (message_id, user_id, emoji) VALUES (?, ?, ?)",
            (message_id, user_id, body.emoji),
        )
        conn.commit()
    except sqlite3.IntegrityError:
        raise conflict(f"You already reacted to message {message_id} with {body.emoji}.")
    return serialize_message(conn, get_message_or_404(conn, message_id), user_id)


@router.delete("/messages/{message_id}/reactions", status_code=204)
def remove_reaction(
    message_id: int,
    emoji: Annotated[Emoji, Query()],
    user_id: str = Depends(current_user),
    conn: sqlite3.Connection = Depends(get_db),
):
    """Removes the caller's own reaction. The WHERE clause includes user_id, so
    nobody can ever remove someone else's."""
    message = get_message_or_404(conn, message_id)
    require_channel_writable(conn, message["channel_id"])
    cur = conn.execute(
        "DELETE FROM reactions WHERE message_id = ? AND user_id = ? AND emoji = ?",
        (message_id, user_id, emoji),
    )
    conn.commit()
    if cur.rowcount == 0:
        raise not_found(f"You have no {emoji} reaction on message {message_id}.")
    return Response(status_code=204)
