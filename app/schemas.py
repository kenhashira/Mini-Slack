"""Request bodies. Response bodies are plain dicts built in the routers."""
from typing import Annotated

from pydantic import BaseModel, StringConstraints

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
