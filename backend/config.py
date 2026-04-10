from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    openai_api_key: str = ""
    google_api_key: str = ""
    gemini_api_key: str = ""
    database_url: str = "postgresql+psycopg://postgres:postgres@localhost:5432/smart_meeting_assistant"
    pinecone_api_key: str = ""
    pinecone_index_name: str = "smart-meeting-assistant"
    assignee_email_map: str = "{}"
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_sender: str = ""
    smtp_use_tls: bool = True
    email_subject_prefix: str = "Smart Meeting Assistant"
    email_service_url: str = "http://127.0.0.1:3001"
    backend_host: str = "0.0.0.0"
    backend_port: int = 8000
    capture_service_enabled: bool = False

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
