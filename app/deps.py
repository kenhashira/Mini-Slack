"""Shared request dependencies."""
import sqlite3
from typing import Optional

from fastapi import Depends, Header

from app.db import get_db
from app.errors import unauthorized


def current_user_id(x_user_id: Optional[str] = Header(default=None)) -> str:
    """Identify the caller from the X-User-Id header.

    There is no real authentication: whatever the client sends is trusted.
    A missing or blank header is a 401.
    """
    if x_user_id is None or not x_user_id.strip():
        raise unauthorized("Missing X-User-Id header.")
    return x_user_id.strip()


def current_user(
    user_id: str = Depends(current_user_id),
    conn: sqlite3.Connection = Depends(get_db),
) -> str:
    """Like current_user_id, but also records the user on first sight."""
    conn.execute("INSERT OR IGNORE INTO users (id) VALUES (?)", (user_id,))
    conn.commit()
    return user_id
