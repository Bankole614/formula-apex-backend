import os
from typing import List
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    APP_NAME: str = "Apex Racing GP Backend"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = True
    PORT: int = 8000
    HOST: str = "0.0.0.0"

    # CORS settings: allows local Vite dev server and production domains
    CORS_ORIGINS: List[str] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:4173",
        "http://127.0.0.1:4173",
        "http://localhost:3000",
        "*",  # Permissive for development; restrict in production
    ]

    # Database: Async SQLite database file
    DATABASE_PATH: str = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "data",
        "apex_racing.db",
    )

    # Cloudflare R2 / S3 Storage (Optional: used for game music, 3D glTF models, ghost replays)
    R2_ACCOUNT_ID: str = ""
    R2_ACCESS_KEY_ID: str = ""
    R2_SECRET_ACCESS_KEY: str = ""
    R2_BUCKET_NAME: str = "apex-racing-assets"
    # Public domain or worker URL mapped to your R2 bucket (e.g. https://cdn.yourdomain.com)
    R2_PUBLIC_URL: str = "https://cdn.apex-racing.dev"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()

