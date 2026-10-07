from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict

load_dotenv()


class Settings(BaseSettings):
    database_url: str = "postgresql+psycopg://qd_user:qd_pass@localhost:5433/qd_db"
    payswift_base_url: str = "http://localhost:8081"
    environment: str = "development"
    llm_provider: str = "gemini"  # "gemini" or "groq"
    llm_model: str | None = None
    llm_delay_seconds: int = 5

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


settings = Settings()
