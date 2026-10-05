from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter


class Message(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    id: str = Field(min_length=1, max_length=64)


class Ping(Message):
    type: Literal["ping"]


class Text(Message):
    type: Literal["text"]
    text: str = Field(min_length=1, max_length=4096)


incoming = TypeAdapter(Annotated[Ping | Text, Field(discriminator="type")])
