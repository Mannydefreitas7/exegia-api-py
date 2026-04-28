#!/usr/bin/env python3
"""Start the local Exegia dev stack via Docker Compose.

What this does:
    1. Verifies `docker` and `docker compose` are available and that the
       Docker daemon is reachable.
    2. Reads the dotenvx private keys from `.env.keys` and adds them to the
       process environment passed to `docker compose`. Compose then performs
       its `${DOTENV_PRIVATE_KEY_DEVELOPMENT}` substitution so the running
       container can decrypt `.env.development` at startup with `dotenvx run`.
    3. Builds (unless --no-build) and starts the compose stack in detached mode.
    4. Waits for the dev-gui service to start serving, then opens
       https://dev.exegia.local in your default browser (unless --no-browser).
    5. Optionally follows logs (--logs).

Notes:
    * Requires `.env.keys` next to this project root. That file is gitignored
      and contains the dotenvx private decryption keys.
    * The Supabase local stack is no longer started here — use the hosted
      Supabase project (configured via SUPABASE_URL in `.env.development`).
    * Caddy serves HTTPS via a locally-trusted root cert (`local_certs`). The
      first time you hit https://dev.exegia.local your browser will prompt to
      trust the Caddy root CA — accept it once, or run
      `docker exec py-exegia-caddy-1 caddy trust`.

Hosts file:
    These vhosts must resolve to 127.0.0.1. Add them to /etc/hosts:
        127.0.0.1   api.exegia.local dev.exegia.local

Usage:
    uv run scripts/start.py                # build + start + open browser
    uv run scripts/start.py --no-browser   # don't open browser
    uv run scripts/start.py --logs         # build + start, then follow logs
    uv run scripts/start.py --no-build     # start without rebuilding images
    uv run scripts/start.py --stop         # stop the stack
    uv run scripts/start.py --restart      # down + up
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ENV_KEYS = ROOT / ".env.keys"
ENV_DEV = ROOT / ".env.development"
COMPOSE_FILE = ROOT / "compose.yml"

DEV_GUI_HOST = "dev.exegia.local"
API_HOST = "api.exegia.local"
DEV_GUI_URL = f"https://{DEV_GUI_HOST}"
DEV_GUI_LOCAL_PROBE = "http://127.0.0.1:8080/"
HOSTS_FILE = Path("/etc/hosts")
HOSTS_LINE = f"127.0.0.1\t{API_HOST} {DEV_GUI_HOST}"

# Matches `KEY=value` and `KEY="value"` style lines, ignoring comments/blanks.
_ENV_LINE = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*?)\s*$")


def _strip_quotes(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
        return value[1:-1]
    return value


def load_env_keys() -> dict[str, str]:
    """Parse `.env.keys` into a dict.

    The file is a plain dotenv-style listing of dotenvx private decryption
    keys (e.g. DOTENV_PRIVATE_KEY_DEVELOPMENT). We do not need `dotenvx`
    itself on the host — we just feed the keys to docker compose via env.
    """
    if not ENV_KEYS.is_file():
        sys.exit(
            f"error: {ENV_KEYS.relative_to(ROOT)} not found. This file holds the "
            "dotenvx private decryption keys (DOTENV_PRIVATE_KEY_DEVELOPMENT, …) "
            "and is required to launch the stack. It is gitignored — restore it "
            "from your password manager / team secrets store."
        )

    keys: dict[str, str] = {}
    for raw in ENV_KEYS.read_text().splitlines():
        line = raw.split("#", 1)[0]
        if not line.strip():
            continue
        m = _ENV_LINE.match(line)
        if not m:
            continue
        keys[m.group(1)] = _strip_quotes(m.group(2))

    if "DOTENV_PRIVATE_KEY_DEVELOPMENT" not in keys:
        sys.exit(
            f"error: {ENV_KEYS.relative_to(ROOT)} does not define "
            "DOTENV_PRIVATE_KEY_DEVELOPMENT — add it (run `dotenvx encrypt` to "
            "regenerate the keys file)."
        )
    return keys


def make_env(extra: dict[str, str]) -> dict[str, str]:
    env = os.environ.copy()
    env.update(extra)
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


def ensure_tool(name: str, hint: str) -> None:
    if shutil.which(name) is None:
        sys.exit(f"error: `{name}` is required on PATH. {hint}")


def ensure_docker_daemon() -> None:
    """`docker info` is a cheap ping for the daemon socket."""
    result = subprocess.run(["docker", "info"], capture_output=True, text=True)
    if result.returncode != 0:
        sys.exit(
            "error: Docker daemon is not reachable. Start Docker Desktop "
            "(or your Docker engine) and try again."
        )


def ensure_compose() -> None:
    result = subprocess.run(
        ["docker", "compose", "version"], capture_output=True, text=True
    )
    if result.returncode != 0:
        sys.exit(
            "error: `docker compose` (V2 plugin) is required. "
            "Update Docker Desktop or install the compose plugin."
        )


def ensure_files() -> None:
    if not COMPOSE_FILE.is_file():
        sys.exit(f"error: {COMPOSE_FILE.relative_to(ROOT)} not found.")
    if not ENV_DEV.is_file():
        sys.exit(
            f"error: {ENV_DEV.relative_to(ROOT)} not found. "
            "Generate it with `dotenvx encrypt` against your dev secrets."
        )
    # ENV_KEYS is validated in load_env_keys().


def hostname_resolves(host: str) -> bool:
    try:
        socket.gethostbyname(host)
        return True
    except OSError:
        return False


def warn_unresolved_hosts() -> list[str]:
    """Return the list of hostnames that don't currently resolve."""
    missing = [h for h in (API_HOST, DEV_GUI_HOST) if not hostname_resolves(h)]
    if not missing:
        return []

    print()
    print("⚠  The following hostnames do not resolve on this machine:")
    for h in missing:
        print(f"    - {h}")
    print(
        "   Caddy serves the dev URLs on these vhosts. Add this line to "
        f"{HOSTS_FILE} (requires sudo) so the browser can reach them:\n\n"
        f"       {HOSTS_LINE}\n\n"
        "   On macOS/Linux:\n"
        f'       echo "{HOSTS_LINE}" | sudo tee -a {HOSTS_FILE}\n'
    )
    return missing


def running_services(env: dict[str, str]) -> list[str]:
    """Return the list of compose services currently in the running state."""
    result = subprocess.run(
        [
            "docker", "compose", "-f", str(COMPOSE_FILE),
            "ps", "--status", "running", "--services",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        env=env,
    )
    if result.returncode != 0:
        return []
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def preflight() -> dict[str, str]:
    ensure_tool("docker", "Install Docker Desktop and make sure it is running.")
    ensure_compose()
    ensure_docker_daemon()
    ensure_files()
    return make_env(load_env_keys())


def wait_for_dev_gui(timeout_s: float = 30.0) -> bool:
    """Poll the dev-gui port (via host-published 8080) until it serves a response.

    FastHTML under `--reload` takes a couple of seconds to bind after the
    container reports as Started. Using the host-published 127.0.0.1:8080
    is reliable regardless of whether dev.exegia.local resolves.
    """
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(DEV_GUI_LOCAL_PROBE, timeout=2) as resp:
                if resp.status < 500:
                    return True
        except (urllib.error.URLError, ConnectionError, TimeoutError, OSError):
            pass
        time.sleep(0.5)
    return False


def open_dev_gui(missing_hosts: list[str]) -> None:
    """Open the dev-gui in the default browser."""
    if not wait_for_dev_gui():
        print(
            "\n⚠  dev-gui did not start serving within 30s — skipping browser open. "
            "Check `docker compose logs dev-gui`."
        )
        return

    if DEV_GUI_HOST in missing_hosts:
        fallback = DEV_GUI_LOCAL_PROBE
        print(
            f"\n→ {DEV_GUI_HOST} does not resolve; opening fallback {fallback} instead.\n"
            f"   Add `{HOSTS_LINE}` to {HOSTS_FILE} to use the proxied URL."
        )
        webbrowser.open(fallback, new=2)
        return

    print(f"\n→ Opening {DEV_GUI_URL} in your default browser...")
    webbrowser.open(DEV_GUI_URL, new=2)


def start(*, build: bool, follow_logs: bool, open_browser: bool) -> None:
    env = preflight()
    missing = warn_unresolved_hosts()

    already = running_services(env)
    if already:
        print(f"Stack already running: {', '.join(already)}\n")
        run(
            ["docker", "compose", "-f", str(COMPOSE_FILE), "ps"],
            env=env,
        )
        if open_browser:
            open_dev_gui(missing)
        if follow_logs:
            _follow_logs(env)
        return

    up_cmd = ["docker", "compose", "-f", str(COMPOSE_FILE), "up"]
    if build:
        up_cmd.append("--build")
    up_cmd.append("-d")

    print("Starting Exegia dev stack (this may take a minute on first build)...")
    run(up_cmd, env=env)

    print("\nStack is up. Service status:")
    run(["docker", "compose", "-f", str(COMPOSE_FILE), "ps"], env=env)
    print(
        "\nFastAPI:    http://localhost:8000\n"
        "Swagger UI: http://localhost:8000/docs\n"
        "Health:     http://localhost:8000/health\n"
        f"API (TLS):  https://{API_HOST}\n"
        f"Dev GUI:    {DEV_GUI_URL}  (also http://localhost:8080)"
    )

    if open_browser:
        open_dev_gui(missing)

    if follow_logs:
        _follow_logs(env)


def _follow_logs(env: dict[str, str]) -> None:
    print("\nFollowing logs (Ctrl-C to detach; containers keep running)...")
    try:
        run(
            ["docker", "compose", "-f", str(COMPOSE_FILE),
             "logs", "-f", "--tail", "100"],
            env=env,
            check=False,
        )
    except KeyboardInterrupt:
        print("\nDetached from logs. Stack is still running.")


def stop() -> None:
    env = preflight()
    run(["docker", "compose", "-f", str(COMPOSE_FILE), "down"], env=env)


def restart(*, build: bool, open_browser: bool) -> None:
    stop()
    start(build=build, follow_logs=False, open_browser=open_browser)


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    action = parser.add_mutually_exclusive_group()
    action.add_argument(
        "--stop", action="store_true",
        help="Stop the dev stack (`docker compose down`).",
    )
    action.add_argument(
        "--restart", action="store_true",
        help="Stop, then start the dev stack.",
    )
    parser.add_argument(
        "--no-build", action="store_true",
        help="Skip the image rebuild step on `up`.",
    )
    parser.add_argument(
        "--logs", action="store_true",
        help="Follow container logs after starting.",
    )
    parser.add_argument(
        "--no-browser", action="store_true",
        help=f"Do not open {DEV_GUI_URL} in the browser after start.",
    )
    args = parser.parse_args()

    if args.stop:
        stop()
        return
    if args.restart:
        restart(build=not args.no_build, open_browser=not args.no_browser)
        return
    start(
        build=not args.no_build,
        follow_logs=args.logs,
        open_browser=not args.no_browser,
    )


if __name__ == "__main__":
    main()
