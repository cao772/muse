from typing import Literal

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="MUSE_", env_file=".env", extra="ignore")

    host: str = "127.0.0.1"
    port: int = Field(default=8000, ge=1, le=65535)
    provider: Literal["mock", "deepseek", "qwen", "openai-compatible"] = "mock"
    max_message_bytes: int = Field(default=16384, ge=256, le=1048576)
    device_id: str = Field(default="muse-01", pattern=r"^[a-zA-Z0-9_-]{1,64}$")
    device_token: SecretStr = SecretStr("")
    allowed_hosts: list[str] = ["localhost", "127.0.0.1", "::1", "testserver"]
    allowed_origins: list[str] = []
    max_connections: int = Field(default=2, ge=1, le=32)
    idle_timeout_seconds: float = Field(default=30, ge=0.05, le=300)
    provider_timeout_seconds: float = Field(default=15, ge=0.05, le=120)
    llm_api_key: SecretStr = SecretStr("")
    llm_base_url: str = "https://api.deepseek.com"
    llm_model: str = "deepseek-flash"
    llm_max_tokens: int = Field(default=256, ge=1, le=4096)
    stt_provider: Literal["mock", "mlx-whisper"] = "mock"
    stt_model: str = "mlx-community/whisper-large-v3-turbo"

    @model_validator(mode="after")
    def validate_network_access(self):
        token = self.device_token.get_secret_value()
        if token and (len(token) < 32 or not token.isascii() or any(c.isspace() for c in token)):
            raise ValueError(
                "Device token must contain at least 32 non-whitespace ASCII characters"
            )
        if self.host not in {"localhost", "127.0.0.1", "::1"}:
            if not token or not self.allowed_hosts or "*" in self.allowed_hosts:
                raise ValueError("Non-loopback binding requires a token and explicit allowed_hosts")
        return self
