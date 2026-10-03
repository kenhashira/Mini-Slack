"""Shared request dependencies."""
from typing import Optional

from fastapi import Header

from app.errors import unauthorized


def current_user_id(x_user_id: Optional[str] = Header(default=None)) -> str:
    """Identify the caller from the X-User-Id header.

    There is no real authentication: whatever the client sends is trusted.
    A missing or blank header is a 401.
    """
    if x_user_id is None or not x_user_id.strip():
        raise unauthorized("Missing X-User-Id header.")
    return x_user_id.strip()
