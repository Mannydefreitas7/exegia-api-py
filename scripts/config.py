"""Pydantic-settings configuration for the Exegia API server."""

from __future__ import annotations
import os
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    supabase_project_ref: str = os.getenv("SUPABASE_PROJECT_REF", "")
    supabase_url: str = os.getenv("SUPABASE_URL", "")
    supabase_publishable_key: str = os.getenv("SUPABASE_PUBLISHABLE_KEY", "")
    supabase_service_role_key: str = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
    supabase_storage_bucket: str = os.getenv("SUPABASE_STORAGE_BUCKET", "corpora")
    supabase_secret_key: str = os.getenv("SUPABASE_SECRET_KEY", "")

    database_url: str = os.getenv("DATABASE_URL", "")

    datasets_base_path: str = os.getenv("DATASETS_BASE_PATH", "")

    # Name of the Supabase Edge Function that converts corpus archives.
    convert_corpus_function: str = os.getenv("CONVERT_CORPUS_FUNCTION", "convert-corpus")

    environment: str = os.getenv("ENVIRONMENT", "")
    cors_origins: str = os.getenv("CORS_ORIGINS", "*")

    open_ai_key: str = os.getenv("OPEN_AI_KEY", "")

    uv_index_exegia_url: str = os.getenv("UV_INDEX_EXEGIA_URL", "")
    exegia_pypi_publish_url: str = os.getenv("EXEGIA_PYPI_PUBLISH_URL", "")
    github_token: str = os.getenv("GITHUB_TOKEN", "")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
