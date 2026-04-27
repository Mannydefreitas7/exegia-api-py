"""Pydantic-settings configuration for the Exegia API server."""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    supabase_url: str = Field(default="", alias="SUPABASE_URL")
    supabase_anon_key: str = Field(default="", alias="SUPABASE_ANON_KEY")
    supabase_service_role_key: str = Field(
        default="", alias="SUPABASE_SERVICE_ROLE_KEY"
    )
    supabase_storage_bucket: str = Field(
        default="corpora", alias="SUPABASE_STORAGE_BUCKET"
    )
    database_url: str = Field(default="", alias="DATABASE_URL")

    # Name of the Supabase Edge Function that converts corpus archives.
    convert_corpus_function: str = Field(
        default="convert-corpus", alias="CONVERT_CORPUS_FUNCTION"
    )

    environment: str = Field(default="development", alias="ENVIRONMENT")
    cors_origins: str = Field(default="*", alias="CORS_ORIGINS")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
