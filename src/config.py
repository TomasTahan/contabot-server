from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # Telegram
    telegram_bot_token: str

    # PocketBase
    pocketbase_url: str
    pocketbase_admin_email: str
    pocketbase_admin_password: str

    # Groq
    groq_api_key: str

    # Server
    webhook_url: str = ""
    host: str = "0.0.0.0"
    port: int = 8000

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache
def get_settings() -> Settings:
    return Settings()
