#!/usr/bin/env python3
"""Installation script for the Exegia backend.

Steps:
    1. Install workspace dependencies via `uv sync`.
    2. Install `dotenvx` for reading the encrypted .env files.
    3. Generate a self-signed SSL certificate for local Supabase HTTPS dev
       (matches `[api.tls]` in supabase/config.toml).

Run via `uv run scripts/setup.py` so the sync'd venv is active when step 3
imports pyOpenSSL.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
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
    print("\n[1/3] Syncing workspace dependencies...")
    run(["uv", "sync"])


def install_dotenvx() -> None:
    """Add dotenvx to the project so encrypted .env values can be decrypted.

    `uv add` is idempotent — if dotenvx is already pinned in pyproject.toml it
    just reconciles the version and updates the lockfile.
    """
    print("\n[2/3] Installing dotenvx (encrypted .env loader)...")
    run(["uv", "add", "dotenvx"])


def generate_ssl_certs() -> None:
    """Generate a self-signed cert/key into `supabase/` for local HTTPS.

    Delegates to `scripts/generate_ssl.py`; cwd is pinned to ROOT because that
    module writes paths relative to the current working directory.
    """
    print("\n[3/3] Generating self-signed SSL certificate for local Supabase...")
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


def main() -> None:
    ensure_uv()
    sync_dependencies()
    install_dotenvx()
    generate_ssl_certs()

    print("\nSetup complete.")
    print(
        "Next: set SUPABASE_URL and SUPABASE_KEY in your .env "
        "(see .env.example), then initialize with:\n"
        "    from supabase import create_client, Client\n"
        "    supabase: Client = create_client(url, key)"
    )


if __name__ == "__main__":
    main()
