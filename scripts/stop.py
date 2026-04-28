#!/usr/bin/env python3
"""Stop the local Exegia dev stack.

Tears down the Docker Compose stack (FastAPI app, dev-gui, caddy) defined in
`compose.yml`. The decryption keys in `.env.keys` are loaded into the process
environment so Compose's `${DOTENV_PRIVATE_KEY_DEVELOPMENT}` substitution
succeeds during teardown the same way it does on `up`.

By default this runs `docker compose down`, which stops and removes
containers + the project network but preserves named volumes (caddy_data,
caddy_config). Pass `--volumes` to also drop those volumes.

Usage:
    uv run scripts/stop.py                # stop containers, keep volumes
    uv run scripts/stop.py --volumes      # also remove named volumes
    uv run scripts/stop.py --kill-uvicorn # additionally kill any host-side
                                          # uvicorn processes started outside
                                          # the container (legacy workflow)
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ENV_KEYS = ROOT / ".env.keys"
COMPOSE_FILE = ROOT / "compose.yml"

_ENV_LINE = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*?)\s*$")


def _strip_quotes(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
        return value[1:-1]
    return value


def load_env_keys() -> dict[str, str]:
    """Best-effort parse of `.env.keys`.

    Unlike `start.py`, we don't hard-fail if the file is missing — `down`
    should still work as long as Compose has values to substitute. We *do*
    fail if the file exists but doesn't contain DOTENV_PRIVATE_KEY_DEVELOPMENT,
    because that means it's malformed.
    """
    if not ENV_KEYS.is_file():
        return {}

    keys: dict[str, str] = {}
    for raw in ENV_KEYS.read_text().splitlines():
        line = raw.split("#", 1)[0]
        if not line.strip():
            continue
        m = _ENV_LINE.match(line)
        if not m:
            continue
        keys[m.group(1)] = _strip_quotes(m.group(2))
    return keys


def make_env(extra: dict[str, str]) -> dict[str, str]:
    env = os.environ.copy()
    env.update(extra)
    # Provide a harmless default so Compose's ${VAR:?…} substitution succeeds
    # during `down` even if the user lost their .env.keys. We only need to
    # *parse* compose.yml for the down command — no decryption happens here.
    env.setdefault("DOTENV_PRIVATE_KEY_DEVELOPMENT", "stop-placeholder")
    env.setdefault("DOTENV_PRIVATE_KEY", "")
    return env


def run(
    cmd: list[str],
    env: dict[str, str] | None = None,
    *,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    print(f"$ {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=ROOT, text=True, env=env)
    if check and result.returncode != 0:
        sys.exit(result.returncode)
    return result


def ensure_docker() -> None:
    if shutil.which("docker") is None:
        sys.exit(
            "error: `docker` is required on PATH. "
            "Install Docker Desktop and make sure it is running."
        )
    info = subprocess.run(["docker", "info"], capture_output=True, text=True)
    if info.returncode != 0:
        sys.exit(
            "error: Docker daemon is not reachable. Start Docker Desktop "
            "(or your Docker engine) and try again."
        )
    ver = subprocess.run(
        ["docker", "compose", "version"], capture_output=True, text=True
    )
    if ver.returncode != 0:
        sys.exit(
            "error: `docker compose` (V2 plugin) is required. "
            "Update Docker Desktop or install the compose plugin."
        )


def stop_compose(*, with_volumes: bool) -> None:
    if not COMPOSE_FILE.is_file():
        sys.exit(f"error: {COMPOSE_FILE.relative_to(ROOT)} not found.")
    ensure_docker()

    env = make_env(load_env_keys())
    cmd = ["docker", "compose", "-f", str(COMPOSE_FILE), "down"]
    if with_volumes:
        cmd.append("--volumes")
    run(cmd, env=env)


def kill_host_uvicorn() -> None:
    """Legacy: terminate any host-side uvicorn processes for this project.

    The current dev workflow runs uvicorn *inside* the `app` container, so
    this is normally a no-op. Kept as an opt-in escape hatch (`--kill-uvicorn`)
    in case someone still launches uvicorn directly on the host.
    """
    if shutil.which("pkill") is None:
        print("pkill not available — skipping host uvicorn cleanup.")
        return
    pattern = f"uvicorn.*{ROOT}"
    result = subprocess.run(
        ["pkill", "-f", pattern], capture_output=True, text=True
    )
    if result.returncode == 0:
        print(f"Terminated host uvicorn processes matching {pattern!r}.")
    elif result.returncode == 1:
        print("No host-side uvicorn processes found.")
    else:
        print(
            f"warning: pkill exited {result.returncode}: {result.stderr.strip()}",
            file=sys.stderr,
        )


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--volumes",
        action="store_true",
        help="Also remove named volumes (caddy_data, caddy_config).",
    )
    parser.add_argument(
        "--kill-uvicorn",
        action="store_true",
        help="Additionally pkill any host-side uvicorn processes "
             "(legacy non-Docker workflow).",
    )
    args = parser.parse_args()

    stop_compose(with_volumes=args.volumes)
    if args.kill_uvicorn:
        kill_host_uvicorn()

    print("\nDone.")


if __name__ == "__main__":
    main()
