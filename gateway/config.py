from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="MUSE_", env_file=".env", extra="ignore")

    host: str = "127.0.0.1"
    port: int = Field(default=8000, ge=1, le=65535)
    provider: Literal["mock", "deepseek", "qwen", "openai-compatible"] = "mock"
    max_message_bytes: int = Field(default=16384, ge=256, le=1048576)
