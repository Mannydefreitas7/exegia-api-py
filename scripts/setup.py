#!/usr/bin/env python3
"""Installation script for the Exegia backend.

Steps:
    1. Install workspace dependencies via `uv sync`.
    2. Install `dotenvx` for reading the encrypted .env files.
    3. Generate a self-signed SSL certificate for local Supabase HTTPS dev
       (matches `[api.tls]` in supabase/config.toml).
    4. Pull DOTENV_PRIVATE_* secrets from Supabase and merge into .env.keys
       (requires SUPABASE_ACCESS_TOKEN env var; skipped if absent).

Run via `uv run scripts/setup.py` so the sync'd venv is active when step 3
imports pyOpenSSL.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent
ROOT = SCRIPTS_DIR.parent


def run(cmd: list[str]) -> None:
    print(f"$ {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=ROOT)
    if result.returncode != 0:
        sys.exit(result.returncode)


def ensure_uv() -> None:
    if shutil.which("uv") is None:
        sys.exit("error: `uv` is required. Install from https://docs.astral.sh/uv/")


def sync_dependencies() -> None:
    print("\n[1/4] Syncing workspace dependencies...")
    run(["uv", "sync"])


def install_dotenvx() -> None:
    """Add dotenvx to the project so encrypted .env values can be decrypted.

    `uv add` is idempotent — if dotenvx is already pinned in pyproject.toml it
    just reconciles the version and updates the lockfile.
    """
    print("\n[2/4] Installing dotenvx (encrypted .env loader)...")
    run(["uv", "add", "dotenvx"])


def generate_ssl_certs() -> None:
    """Generate a self-signed cert/key into `supabase/` for local HTTPS.

    Delegates to `scripts/generate_ssl.py`; cwd is pinned to ROOT because that
    module writes paths relative to the current working directory.
    """
    print("\n[3/4] Generating self-signed SSL certificate for local Supabase...")
    if str(SCRIPTS_DIR) not in sys.path:
        sys.path.insert(0, str(SCRIPTS_DIR))
    from generate_ssl import generate_ssl_cert

    previous_cwd = Path.cwd()
    os.chdir(ROOT)
    try:
        cert_path, key_path = generate_ssl_cert()
    finally:
        os.chdir(previous_cwd)
    print(f"  wrote {cert_path}")
    print(f"  wrote {key_path}")


def _supabase_project_ref() -> str:
    config_path = ROOT / "supabase" / "config.toml"
    for line in config_path.read_text().splitlines():
        stripped = line.strip()
        if stripped.startswith("project_id") and "=" in stripped:
            return stripped.split("=", 1)[1].strip().strip('"').strip("'")
    raise RuntimeError("project_id not found in supabase/config.toml")


def _merge_env_keys(keys: dict[str, str]) -> None:
    env_keys_path = ROOT / ".env.keys"

    if env_keys_path.exists():
        lines = env_keys_path.read_text().splitlines()
    else:
        lines = [
            "#/------------------!DOTENV_PRIVATE_KEYS!-------------------/",
            "#/ private decryption keys. DO NOT commit to source control /",
            "#/     [how it works](https://dotenvx.com/encryption)       /",
            "#/----------------------------------------------------------/",
            "",
        ]

    existing_index: dict[str, int] = {}
    for i, line in enumerate(lines):
        if "=" in line and not line.startswith("#"):
            name = line.split("=", 1)[0].strip()
            if name in keys:
                existing_index[name] = i

    new_entries: list[str] = []
    for name, value in keys.items():
        if name in existing_index:
            lines[existing_index[name]] = f"{name}={value}"
        else:
            new_entries.append(f"{name}={value}")

    if new_entries:
        lines.append("")
        lines.extend(new_entries)

    env_keys_path.write_text("\n".join(lines) + "\n")


def pull_supabase_secrets() -> None:
    """Fetch DOTENV_PRIVATE_* secrets from Supabase and merge into .env.keys.

    Requires SUPABASE_ACCESS_TOKEN (a personal access token from
    https://supabase.com/dashboard/account/tokens). Skipped silently when the
    token is absent so the script stays usable without network access.
    """
    print("\n[4/4] Pulling DOTENV_PRIVATE_* secrets from Supabase...")

    access_token = os.environ.get("SUPABASE_ACCESS_TOKEN")
    if not access_token:
        print("  skipping: SUPABASE_ACCESS_TOKEN not set")
        return

    project_ref = _supabase_project_ref()
    url = f"https://api.supabase.com/v1/projects/{project_ref}/secrets"
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {access_token}"})
    with urllib.request.urlopen(req) as resp:
        secrets: list[dict[str, str]] = json.loads(resp.read())

    private_keys = {s["name"]: s["value"] for s in secrets if s["name"].startswith("DOTENV_PRIVATE_")}

    if not private_keys:
        print("  no DOTENV_PRIVATE_* secrets found in project")
        return

    _merge_env_keys(private_keys)
    print(f"  wrote {len(private_keys)} key(s) to .env.keys")


def main() -> None:
    ensure_uv()
    sync_dependencies()
    install_dotenvx()
    generate_ssl_certs()
    pull_supabase_secrets()

    print("\nSetup complete.")
    print(
        "Next: set SUPABASE_URL and SUPABASE_KEY in your .env "
        "(see .env.example), then initialize with:\n"
        "    from supabase import create_client, Client\n"
        "    supabase: Client = create_client(url, key)"
    )


if __name__ == "__main__":
    main()
