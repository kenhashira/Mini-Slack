"""Request bodies. Response bodies are plain dicts built in the routers."""
from typing import Annotated

from pydantic import BaseModel, Field, StringConstraints

ChannelName = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=80,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]*$",
    ),
]


class ChannelCreate(BaseModel):
    name: ChannelName


MessageBody = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=4000)
]


class MarkRead(BaseModel):
    message_id: int | None = Field(default=None, ge=1)


Emoji = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=64)]


class ReactionCreate(BaseModel):
    emoji: Emoji


class MessageCreate(BaseModel):
    body: MessageBody


class MessageEdit(BaseModel):
    body: MessageBody
