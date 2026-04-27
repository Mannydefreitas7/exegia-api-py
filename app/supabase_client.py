"""Lazily-created Supabase clients shared across requests.

Self-contained so it can be imported without triggering the exegia package
init (which calls create_app() and would create a circular import).
"""

from __future__ import annotations

from functools import lru_cache

from supabase import Client, create_client
from supabase.client import SyncClientOptions

from app.config import get_settings


def _make_client(url: str, key: str) -> Client:
    if not key:
        raise RuntimeError(
            "Supabase key is missing. Set SUPABASE_ANON_KEY / "
            "SUPABASE_SERVICE_ROLE_KEY in your environment."
        )
    return create_client(
        url,
        key,
        options=SyncClientOptions(
            auto_refresh_token=False,
            persist_session=False,
        ),
    )


@lru_cache(maxsize=1)
def get_anon_client() -> Client:
    s = get_settings()
    return _make_client(s.supabase_url, s.supabase_anon_key)


@lru_cache(maxsize=1)
def get_service_client() -> Client:
    s = get_settings()
    return _make_client(s.supabase_url, s.supabase_service_role_key)
