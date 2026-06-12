from pydantic_settings import BaseSettings, SettingsConfigDict

ALLOWED_ORIGINS = [
    "http://localhost:3000",
    "http://localhost:5173",
]


class Settings(BaseSettings):
    DATABASE_URL: str
    SECRET_KEY: str
    DEBUG: bool = False
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    IN_REVIEW_TIMEOUT_MINUTES: int = 30
    B2B_BASE_URL: str = "http://b2b:8000"
    MOD_TO_B2B_SERVICE_KEY: str
    B2B_TO_MOD_SERVICE_KEY: str

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
