"""Central configuration. Secrets come from env / vault — never hardcoded."""
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    DATABASE_URL: str = "sqlite:///./aibos.db"
    REDIS_URL: str = "redis://localhost:6379/0"
    API_SECRET: str = "dev-only-secret-change-me"
    ENV: str = "development"
    KILL_SWITCH_KEY: str = "aibos:kill_switch"

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
