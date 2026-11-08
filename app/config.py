"""Application settings, read from environment variables (or a .env file)."""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # SQLite by default so the app runs locally with zero setup;
    # docker-compose points this to PostgreSQL.
    database_url: str = "sqlite:///./data/analyzer.db"
    upload_dir: Path = Path("data/uploads")

    ollama_url: str = "http://localhost:11434"
    default_model: str = "qwen3.5:4b"

    # --- Resource tuning for a 6 GB GPU ---
    # Vision encoders downscale large images anyway; sending fewer pixels
    # saves upload time, image tokens and VRAM.
    max_image_side: int = 1024
    # A small context window keeps the KV cache small (an image + prompt
    # + JSON answer fits comfortably in 4k tokens).
    num_ctx: int = 4096
    # How long Ollama keeps the model in VRAM after a request.
    keep_alive: str = "5m"
    request_timeout_s: float = 300


settings = Settings()
