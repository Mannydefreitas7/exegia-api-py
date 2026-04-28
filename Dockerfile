# ── Stage 1: build the virtualenv ────────────────────────────────────────────
FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim AS builder

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

WORKDIR /app

# Install dependencies from the lockfile only — keeps cache hits when only
# source files change. The project itself is not installed yet.
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --frozen --no-install-project --no-dev

# Now copy the source and install the project (editable by default in uv,
# which lets bind-mounted source in compose hot-reload through the venv).
COPY pyproject.toml uv.lock README.md ./
COPY main.py ./
COPY src ./src
COPY scripts ./scripts
# Encrypted env file — safe to bake in, values are AES-encrypted and only
# decryptable with DOTENV_PRIVATE_KEY_* (provided at runtime via env).
COPY .env.development ./

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev

# ── Stage 2: runtime ────────────────────────────────────────────────────────
FROM python:3.13-slim-bookworm AS runtime

# Install dotenvx binary and supabase cli (standalone CLIs).
RUN apt-get update -qq && \
    apt-get install -y --no-install-recommends curl ca-certificates && \
    curl -sfS https://dotenvx.sh/install.sh | DOTENVX_INSTALL_DIR=/usr/local/bin sh && \
    ARCH=$(dpkg --print-architecture) && \
    if [ "$ARCH" = "amd64" ]; then SU_ARCH="amd64"; elif [ "$ARCH" = "arm64" ]; then SU_ARCH="arm64"; else echo "Unsupported architecture" && exit 1; fi && \
    curl -sfL "https://github.com/supabase/cli/releases/latest/download/supabase_linux_${SU_ARCH}.tar.gz" | tar -xz -C /usr/local/bin supabase && \
    apt-get purge -y --auto-remove curl && \
    rm -rf /var/lib/apt/lists/*

# Drop privileges — never run as root in containers.
RUN groupadd --system app && useradd --system --gid app --create-home app

WORKDIR /app

# Bring in the venv + source from the builder.
COPY --from=builder --chown=app:app /app /app

# Make the venv the default Python environment.
ENV PATH="/app/.venv/bin:${PATH}" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

USER app

EXPOSE 8000 8080

# Healthcheck hits FastAPI's /health route (defined in src/exegia/__init__.py).
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request,sys; \
        sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3).status==200 else 1)"

# Decrypt .env.development at runtime. The DOTENV_PRIVATE_KEY_DEVELOPMENT (or
# the generic DOTENV_PRIVATE_KEY) must be supplied via the process env — see
# compose.yml. The encrypted file itself ships in the image at /app/.env.development.
CMD ["dotenvx", "run", "-f", ".env.development", "--", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
