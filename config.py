import os
from pathlib import Path
from pydantic import ConfigDict
from pydantic_settings import BaseSettings

BASE_DIR = Path(__file__).resolve().parent


class Settings(BaseSettings):
    APP_TITLE: str = "Standalone Departmental Budget & Savings Analytics"
    DATABASE_URL: str = f"sqlite:///{(BASE_DIR / 'budget_standalone.db').as_posix()}"
    SECRET_KEY: str = os.getenv("BUDGET_SECRET_KEY", "standalone-budget-analytics-secret-key-2026")
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7  # 7 days
    PORT: int = int(os.getenv("BUDGET_PORT", "8060"))
    HOST: str = os.getenv("BUDGET_HOST", "0.0.0.0")

    model_config = ConfigDict(env_file=".env", extra="ignore")


settings = Settings()
