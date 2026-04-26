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

# Now copy the source and install the project (no-op for non-package layouts,
# but keeps the workflow consistent if pyproject is later promoted).
COPY pyproject.toml uv.lock ./
COPY main.py ./
COPY src ./src

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev

# ── Stage 2: runtime ────────────────────────────────────────────────────────
FROM python:3.13-slim-bookworm AS runtime

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

EXPOSE 8000

# Healthcheck hits FastAPI's /health route (defined in main.py).
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request,sys; \
        sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3).status==200 else 1)"

CMD ["dotenvx", "run", "--", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
