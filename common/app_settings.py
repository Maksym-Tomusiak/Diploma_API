from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class AppSettings(BaseSettings):
    DB_CONNECTION_STRING: str = Field(alias="DB_CONNECTION_STRING", min_length=1)
    GOOGLE_CLIENT_ID: str = Field(default="")
    GOOGLE_CLIENT_SECRET: str = Field(default="")
    SECRET_KEY: str = Field(default="supersecretkeychangeme")

    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore"  # ✅ Ignore extra env vars
    )


settings = AppSettings()  # Simple instantiation loads .env automatically
