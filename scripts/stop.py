#!/usr/bin/env python3
"""Stop local dev servers/services while preserving caches and data.

This is the counterpart to `start.py`. It stops what `start.py` starts — plus
any FastAPI/uvicorn dev processes launched from this project — without touching
on-disk state. For a destructive wipe (venv, caches, artifacts) use `clean.py`.

Preserved:
    - Supabase Docker volumes (database rows, storage blobs, auth users)
    - Context-Fabric `.cfm` caches and any `__pycache__` / build artifacts
    - Local `.env.*` files and generated SSL certs

Stopped:
    - Supabase local stack (`supabase stop`)
    - Uvicorn/FastAPI processes whose command line references this project

Usage:
    uv run scripts/stop.py
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = ".env.development"


def dotenvx_wrap(cmd: list[str]) -> list[str]:
    """Wrap a command with `dotenvx run -f .env.development --`."""
    return ["dotenvx", "run", "-f", ENV_FILE, "--", *cmd]


def run(cmd: list[str], check: bool = True) -> subprocess.CompletedProcess[str]:
    print(f"$ {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=ROOT, text=True)
    if check and result.returncode != 0:
        sys.exit(result.returncode)
    return result


def ensure_tool(name: str, hint: str) -> None:
    if shutil.which(name) is None:
        sys.exit(f"error: `{name}` is required on PATH. {hint}")


def is_stack_running() -> bool:
    """`supabase status` exits non-zero when the stack is down."""
    result = subprocess.run(
        dotenvx_wrap(["supabase", "status"]),
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    return result.returncode == 0


def stop_dev_processes() -> None:
    """Terminate any uvicorn processes whose command line references this project.

    Scoping by project path keeps the script from killing unrelated dev servers
    running on the same machine.
    """
    if shutil.which("pkill") is None:
        return
    pattern = f"uvicorn.*{ROOT}"
    result = subprocess.run(["pkill", "-f", pattern], capture_output=True, text=True)
    # pkill exits 0 when a process was signalled, 1 when none matched.
    if result.returncode == 0:
        print(f"Terminated uvicorn processes matching {pattern!r}.")
    elif result.returncode not in (0, 1):
        print(f"warning: pkill exited {result.returncode}: {result.stderr.strip()}", file=sys.stderr)


def stop_supabase() -> None:
    """Stop the local Supabase stack. Docker volumes are preserved by default."""
    if not is_stack_running():
        print("Supabase local stack is not running — nothing to stop.")
        return
    print("Stopping Supabase local stack (database + storage volumes preserved)...")
    run(dotenvx_wrap(["supabase", "stop"]))


def main() -> None:
    argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    ).parse_args()

    ensure_tool(
        "dotenvx",
        "Install: `uv add dotenvx` (already in setup.py) or https://dotenvx.com/docs/install",
    )
    ensure_tool(
        "supabase",
        "Install: https://supabase.com/docs/guides/local-development/cli/getting-started",
    )

    stop_dev_processes()
    stop_supabase()

    print("\nAll services stopped. Caches and data are preserved.")


if __name__ == "__main__":
    main()
