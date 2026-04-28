# Exegia Backend

> Graph-based biblical and religious text study API — powered by Context-Fabric, FastAPI, Strawberry GraphQL, and FastMCP.

---

## What is this?

Exegia is a backend for studying annotated religious texts (Bible, Quran, Tanakh, commentaries, lexicons). It exposes corpus data through three surfaces:

| Surface         | Technology           | Use case                                     |
| --------------- | -------------------- | -------------------------------------------- |
| **REST API**    | FastAPI              | Health, corpora upload/list, generic clients |
| **GraphQL API** | Strawberry + FastAPI | Frontend apps, structured queries            |
| **MCP server**  | FastMCP              | AI assistants (Claude, GPT, etc.)            |

Corpora are loaded from [Context-Fabric](https://context-fabric.ai) — a graph-based annotated text engine. Every word, verse, chapter, and book is a typed node in a graph with queryable features (lemma, morphology, gloss, etc.).

Persistent storage and auth are delegated to a **hosted Supabase project** (configured via `SUPABASE_URL` in `.env.development`). There is no local Supabase stack.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                         Clients                             │
│       Frontend     │   AI Assistant    │   CLI / Script     │
└────────┬───────────┴────────┬──────────┴────────┬───────────┘
         │                    │                   │
   GraphQL (Strawberry)  MCP (FastMCP)      REST (FastAPI)
         │                    │                   │
┌────────▼────────────────────▼───────────────────▼───────────┐
│                       exegia package                        │
│    .graphql   │   .mcp   │   .corpus   │   .utils           │
└───────────────────────────┬─────────────────────────────────┘
                            │
           ┌────────────────▼────────────────┐
           │      Context-Fabric (cfabric)   │
           │   F · E · L · T · S · N · C     │
           └────────────────┬────────────────┘
                            │
           ┌────────────────▼────────────────┐
           │         corpus datasets         │
           │   ~/.exegia/datasets/...        │
           └─────────────────────────────────┘
```

The dev runtime is containerised:

```
┌─────────────────────────── docker compose ──────────────────────────┐
│                                                                     │
│   caddy ─► app (FastAPI / GraphQL / MCP, uvicorn --reload)          │
│              ▲                                                      │
│              │                                                      │
│         dev-gui (NiceGUI test harness, scripts/dev_gui.py)          │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Package modules

Everything lives in the `exegia` namespace (`src/exegia/`):

| Module           | Purpose                                         |
| ---------------- | ----------------------------------------------- |
| `exegia.mcp`     | FastMCP server — 11 corpus tools for AI clients |
| `exegia.graphql` | Strawberry GraphQL schema over corpus data      |
| `exegia.corpus`  | Fetch TF datasets from git repositories         |
| `exegia.utils`   | EPUB / HTML → Text-Fabric converters            |
| `exegia.models`  | Shared enums and data model definitions         |
| `exegia.schemas` | Pydantic request/response schemas               |
| `exegia.auth`    | Auth utilities                                  |

---

## Tech stack

- **Python 3.13+** with [uv](https://docs.astral.sh/uv/) for dependency management
- **FastAPI** — HTTP framework
- **Strawberry GraphQL** — schema-first GraphQL with full type safety
- **FastMCP 2** — MCP server for AI clients
- **Context-Fabric** (`cfabric`) — graph corpus engine (fork of Text-Fabric)
- **Supabase (hosted)** — auth + storage, accessed via the `supabase` Python client
- **Docker Compose + Caddy** — local dev runtime
- **dotenvx** — encrypted env files (`.env.development` + `.env.keys`)

---

## Getting started

### Prerequisites

- [uv](https://docs.astral.sh/uv/) ≥ 0.9
- Python 3.13
- Docker Desktop (or any Docker engine) with the `docker compose` V2 plugin
- `.env.keys` from your team's secret store — required to decrypt `.env.development`

### Install

```bash
git clone <repo-url>
cd backend
uv run scripts/setup.py
```

`setup.py` runs `uv sync` (installs all deps, including the `dotenvx` Python wrapper).

### Environment

The repo ships with two env files at the project root:

| File               | Tracked in git? | Contents                                                           |
| ------------------ | --------------- | ------------------------------------------------------------------ |
| `.env.example`     | ✅              | Plain placeholders, copy-as-reference                              |
| `.env.development` | ✅              | dotenvx-**encrypted** values (safe to commit)                      |
| `.env.keys`        | ❌ (gitignored) | dotenvx **private** decryption keys — get from your secret manager |

You don't need to copy `.env.example` to `.env`. The dev workflow always reads `.env.development` (encrypted) using a key from `.env.keys`.

To rotate or add a value:

```bash
# Encrypt a new value into .env.development
uv run dotenvx set MY_NEW_VAR "secret-value" -f .env.development

# Decrypt locally for inspection (does NOT mutate the file)
uv run dotenvx get MY_NEW_VAR -f .env.development
```

### Run the dev stack (Docker Compose)

The recommended path for day-to-day development. Brings up the FastAPI app (with `--reload`), the optional NiceGUI test harness, and Caddy as a local TLS reverse proxy.

```bash
uv run scripts/start.py             # build + start (detached)
uv run scripts/start.py --logs      # build + start, then follow logs
uv run scripts/start.py --no-build  # skip rebuild, start cached image
uv run scripts/start.py --restart   # down + up
uv run scripts/start.py --stop      # equivalent to scripts/stop.py
```

`start.py`:

1. Verifies `docker` + `docker compose` are available and the daemon is reachable.
2. Reads `.env.keys` and feeds `DOTENV_PRIVATE_KEY_DEVELOPMENT` into the Compose process env so `${VAR:?…}` substitution succeeds.
3. Runs `docker compose up [--build] -d`.
4. Inside each container, the entrypoint is `dotenvx run -f .env.development -- …`, which decrypts the env file at startup using the private key.

Once up:

| URL                              | What                          |
| -------------------------------- | ----------------------------- |
| http://localhost:8000            | FastAPI root                  |
| http://localhost:8000/health     | Health probe                  |
| http://localhost:8000/docs       | Swagger UI                    |
| http://localhost:8000/graphql    | GraphQL endpoint + GraphiQL   |
| http://localhost:8080            | NiceGUI dev harness (dev-gui) |
| https://api.exegia.local         | Caddy reverse-proxied (TLS)   |

To stop:

```bash
uv run scripts/stop.py              # docker compose down
uv run scripts/stop.py --volumes    # also drop named volumes (caddy_data, caddy_config)
uv run scripts/stop.py --kill-uvicorn  # legacy: kill any host uvicorn too
```

### Run the API directly (no Docker)

Useful for fast Python-only iteration without rebuilding images:

```bash
uv run dotenvx run -f .env.development -- uvicorn main:app --reload
```

This requires `.env.keys` to be present so `dotenvx` can decrypt values into the process env.

---

## REST API (FastAPI)

The HTTP surface is mounted at the FastAPI root.

| Endpoint   | Description                       |
| ---------- | --------------------------------- |
| `/health`  | Liveness probe — used by Docker   |
| `/docs`    | Swagger UI (auto-generated)       |
| `/graphql` | GraphQL endpoint (see next section) |

Additional routers under `src/exegia/routers/` (e.g. corpora upload/list) are wired in `src/exegia/__init__.py`.

---

## GraphQL API

The schema exposes a corpus hierarchy: `Corpus → Book → Chapter → Verse → Word`.

**Endpoint:** `POST /graphql`

### Example queries

```graphql
# Fetch a passage
query {
  passage(corpus: "BHSA", reference: "Genesis 1:1-3") {
    reference
    text
    words {
      text
      lemma
      partOfSpeech
      gloss
    }
  }
}

# Morphological word search
query {
  words(corpus: "BHSA", filter: { book: "Genesis", partOfSpeech: "verb", verbTense: "perfect" }, limit: 50) {
    text
    lemma
    gloss
  }
}

# Raw Context-Fabric pattern search
query {
  search(corpus: "BHSA", pattern: "word pos=verb\n  book name=Genesis") {
    reference
    text
  }
}
```

### GraphQL types

| Type          | Key fields                                                                                                        |
| ------------- | ----------------------------------------------------------------------------------------------------------------- |
| `Corpus`      | `name`, `nodeTypes`, `featureCount`, `books`                                                                      |
| `Book`        | `name`, `chapters`                                                                                                |
| `Chapter`     | `reference`, `verses`                                                                                             |
| `Verse`       | `reference`, `text`, `words`                                                                                      |
| `Word`        | `text`, `lemma`, `partOfSpeech`, `gloss`, `gender`, `number`, `person`, `verbStem`, `verbTense`, `feature(name)` |
| `SearchMatch` | `reference`, `text`                                                                                               |

Field names use natural language (`lemma`, `partOfSpeech`) instead of raw corpus shorthand (`lex`, `sp`). Use the `feature(name)` escape hatch to access any raw feature directly.

---

## MCP server

The MCP server lets AI assistants query corpora directly via the [Model Context Protocol](https://modelcontextprotocol.io).

### Start the server

```bash
# stdio — for Claude Desktop and other MCP clients
uv run cf-mcp --corpus ~/.exegia/datasets/bibles/BHSA

# SSE on port 8000 — for remote / desktop app connections
uv run cf-mcp --corpus ~/.exegia/datasets/bibles/BHSA --sse 8000

# Multiple corpora at once
uv run cf-mcp \
  --corpus ~/.exegia/datasets/bibles/BHSA --name BHSA \
  --corpus ~/.exegia/datasets/bibles/GNT  --name GNT
```

### Available tools (11)

| Category  | Tool                  | Description                                              |
| --------- | --------------------- | -------------------------------------------------------- |
| Discovery | `list_corpora`        | List loaded corpora and the active one                   |
| Discovery | `describe_corpus`     | Node types with counts, section hierarchy                |
| Discovery | `list_features`       | Browse features, filter by node type                     |
| Discovery | `describe_feature`    | Metadata + top values by frequency                       |
| Discovery | `get_text_formats`    | Available text encodings with samples                    |
| Search    | `search`              | Pattern search — results / count / statistics / passages |
| Search    | `search_continue`     | Paginate large result sets via cursor                    |
| Search    | `search_csv`          | Export results to a local CSV file                       |
| Search    | `search_syntax_guide` | Inline query syntax documentation                        |
| Data      | `get_passages`        | Retrieve text by section reference                       |
| Data      | `get_node_features`   | Batch feature lookup for a list of nodes                 |

### Recommended workflow for AI agents

```
describe_corpus()           → understand what node types exist
list_features()             → see what annotations are available
search_syntax_guide()       → learn the query language
search(template, "count")   → check scale before fetching results
search(template, "results") → get paginated result set
get_passages(references)    → read the matched text
```

### Programmatic use

```python
from exegia.mcp import mcp, corpus_manager

corpus_manager.load("~/.exegia/datasets/bibles/BHSA", name="BHSA")
mcp.run(transport="sse", host="localhost", port=8000)
```

---

## Corpus datasets

Datasets are Text-Fabric archives extracted locally under `~/.exegia/datasets/`.

### Fetch from git

```python
from exegia.corpus.fetch_from_git import fetch_datasets_from_git

paths = fetch_datasets_from_git("https://github.com/ETCBC/bhsa")
# returns list[Path] of dirs containing otext.tf + otype.tf
```

---

## Importing books (EPUB / HTML)

Books can be converted from EPUB or HTML into Text-Fabric datasets for corpus querying.

```python
from exegia.utils.convert_epub_to_tf import convert_epub_to_tf

tf_path = convert_epub_to_tf(
    epub_path="commentary.epub",
    output_dir="~/.exegia/datasets/books/my-commentary/",
    corpus_name="MyCommentary",
)
```

The converter produces this node hierarchy:

```
book
  chapter          (EPUB spine item / page)
    element        (block HTML element)
      paragraph    (paragraph-like elements)
        word       (slot — smallest unit)
```

The output directory is a valid TF dataset, loadable by the MCP server or GraphQL API immediately:

```bash
uv run cf-mcp --corpus ~/.exegia/datasets/books/my-commentary
```

---

## Development

### Run tests

```bash
uv run pytest
```

### Build the wheel

```bash
uv build --out-dir dist/
```

### Build the Docker image manually

`scripts/start.py` rebuilds for you, but if you need to test image layers in isolation:

```bash
docker buildx build --target runtime -t exegia-api:dev --load .
```

### Generate self-signed certs for the Caddy reverse proxy

```bash
uv run scripts/generate_ssl.py
```

### Publish

```bash
uv run scripts/publish.py          # bump patch, commit, tag, push
uv run scripts/publish.py minor    # bump minor
uv run scripts/publish.py 1.2.3    # explicit version
```

### Project layout

```
backend/
├── pyproject.toml       # Package config (hatchling build)
├── uv.lock
├── main.py              # ASGI entrypoint (`main:app`)
├── Dockerfile           # Multi-stage build: uv (builder) → python:3.13-slim (runtime)
├── compose.yml          # Dev stack: app + dev-gui + caddy
├── Caddyfile            # Reverse proxy + local TLS
├── .env.example         # Plain placeholder env (committed)
├── .env.development     # dotenvx-encrypted env (committed)
├── .env.keys            # dotenvx private keys (gitignored)
├── scripts/
│   ├── setup.py         # `uv sync` + dotenvx bootstrap
│   ├── start.py         # docker compose up (with .env.keys injection)
│   ├── stop.py          # docker compose down (+ optional --volumes)
│   ├── dev_gui.py       # NiceGUI dev harness for the corpora API
│   ├── clean.py         # Remove caches + build artifacts
│   ├── generate_ssl.py  # Self-signed certs for the Caddy proxy
│   ├── publish.py       # Build + publish helper
│   └── work.py          # Git workflow helper
├── .github/
│   └── workflows/
│       └── publish.yml  # CI: build + publish on tag push
├── app/                 # FastAPI app config (config, settings)
└── src/
    └── exegia/
        ├── auth/        # Auth utilities
        ├── corpus/      # Git dataset fetching
        ├── graphql/     # Strawberry GraphQL schema
        ├── mcp/         # FastMCP server (cf-mcp entrypoint)
        ├── models/      # Enums and data model definitions
        ├── routers/     # FastAPI REST routers
        ├── schemas/     # Pydantic API schemas
        └── utils/       # EPUB/HTML → TF converters
```

---

## Troubleshooting

| Symptom                                                                | Likely cause                                                                                                       | Fix                                                                                  |
| ---------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------ |
| `error: .env.keys not found`                                           | The private key file is gitignored and missing on this checkout.                                                   | Restore it from your team's password manager / secrets store.                        |
| `required variable DOTENV_PRIVATE_KEY_DEVELOPMENT is missing a value`  | Compose tried to start but the key wasn't in the env. `start.py` loads `.env.keys` automatically — check that file has the variable. | Verify `.env.keys` contains `DOTENV_PRIVATE_KEY_DEVELOPMENT=…`.                      |
| `error: Docker daemon is not reachable`                                | Docker Desktop / engine is not running.                                                                            | Start Docker Desktop, then re-run `uv run scripts/start.py`.                         |
| `dotenvx: command not found` inside the container                      | Image was built before `dotenvx` was added to the Dockerfile.                                                      | Rebuild: `uv run scripts/start.py` (without `--no-build`).                           |
| Port 8000 / 8080 / 80 / 443 already in use                             | Another local service is bound there.                                                                              | Stop the conflicting service, or edit `compose.yml` host-port mappings.              |
| Healthcheck stuck on `health: starting`                                | App still booting (uvicorn `--reload` import takes a few seconds on first start).                                  | Wait ~15s. If it stays unhealthy, run `docker compose logs app`.                     |

