import sqlite3

from fastapi import APIRouter, Depends

from app.db import get_db
from app.deps import current_user
from app.errors import conflict, not_found
from app.schemas import ChannelCreate

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
    sql = "SELECT * FROM channels"
    if not include_archived:
        sql += " WHERE archived_at IS NULL"
    rows = conn.execute(sql + " ORDER BY name").fetchall()
    return {"channels": [channel_dict(r) for r in rows]}


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
