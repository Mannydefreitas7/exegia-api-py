"""
Lazily-created Supabase clients shared across requests.

Two clients are exposed:
- `get_anon_client()` — uses the publishable anon key, suitable for RLS-bound
  reads of public tables (corpora SELECT policy is `USING (true)`).
- `get_service_client()` — uses the service-role key. Required for admin
  operations such as invoking secure Edge Functions or bypassing RLS.
"""

from __future__ import annotations

from functools import lru_cache

from supabase import Client, create_client
from supabase.lib.client_options import SyncClientOptions

from app.config import Settings, get_settings


def _make_client(url: str, key: str) -> Client:
    """Create a stateless supabase client (no session persistence on the server)."""
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
            persist_session=False
        ),
    )


@lru_cache(maxsize=1)
def get_anon_client() -> Client:
    settings: Settings = get_settings()
    return _make_client(settings.supabase_url, settings.supabase_anon_key)


@lru_cache(maxsize=1)
def get_service_client() -> Client:
    settings: Settings = get_settings()
    return _make_client(settings.supabase_url, settings.supabase_service_role_key)
