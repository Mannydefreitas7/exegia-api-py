# Exegia Backend

> Graph-based biblical and religious text study API — powered by Context-Fabric, FastAPI, Strawberry GraphQL, and FastMCP.

---

## What is this?

Exegia is a backend for studying annotated religious texts (Bible, Quran, Tanakh, commentaries, lexicons). It exposes corpus data through three surfaces:

| Surface | Technology | Use case |
|---------|-----------|----------|
| **GraphQL API** | Strawberry + FastAPI | Frontend apps, structured queries |
| **MCP server** | FastMCP | AI assistants (Claude, GPT, etc.) |
| **REST / Storage** | FastAPI + Supabase | Dataset management, book library |

Corpora are loaded from [Context-Fabric](https://context-fabric.ai) — a graph-based annotated text engine. Every word, verse, chapter, and book is a typed node in a graph with queryable features (lemma, morphology, gloss, etc.).

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
│  .graphql  │  .mcp  │  .auth  │  .schemas  │  .models      │
└───────────────────────────┬─────────────────────────────────┘
                            │
           ┌────────────────▼────────────────┐
           │      Context-Fabric (cfabric)    │
           │   F · E · L · T · S · N · C     │
           └────────────────┬────────────────┘
                            │
           ┌────────────────▼────────────────┐
           │         corpus datasets          │
           │   ~/.exegia/datasets/...         │
           │   (zip archives in Supabase)     │
           └─────────────────────────────────┘
```

---

## Package modules

Everything lives in the `exegia` namespace (`src/exegia/`):

| Module | Purpose |
|--------|---------|
| `exegia.mcp` | FastMCP server — 11 corpus tools for AI clients |
| `exegia.graphql` | Strawberry GraphQL schema over corpus data |
| `exegia.corpus` | Fetch TF datasets from git repositories |
| `exegia.storage` | Supabase Storage client + dataset service |
| `exegia.models` | SQLAlchemy ORM models for the book library |
| `exegia.schemas` | Pydantic request/response schemas |
| `exegia.auth` | JWT + Supabase Auth utilities |
| `exegia.utils` | EPUB / HTML → Text-Fabric converters |
| `exegia.supabase` | Bundled migrations, config, and asset helpers |

---

## Tech stack

- **Python 3.13+** with [uv](https://docs.astral.sh/uv/) for dependency management
- **FastAPI** — HTTP framework
- **Strawberry GraphQL** — schema-first GraphQL with full type safety
- **FastMCP 2** — MCP server for AI clients
- **Context-Fabric** (`cfabric`) — graph corpus engine (fork of Text-Fabric)
- **SQLAlchemy 2 + asyncpg** — async database access
- **Supabase** — auth, database, and object storage
- **Alembic** — database migrations

---

## Getting started

### Prerequisites

- [uv](https://docs.astral.sh/uv/) ≥ 0.9
- Python 3.13
- A running Supabase project (local or cloud)

### Install

```bash
git clone <repo-url>
cd backend
uv sync
```

### Environment

```bash
cp .env.example .env
# fill in SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY, SUPABASE_ANON_KEY
```

### Run the API

```bash
uv run uvicorn main:app --reload
```

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
    words { text lemma partOfSpeech gloss }
  }
}

# Morphological word search
query {
  words(
    corpus: "BHSA"
    filter: { book: "Genesis", partOfSpeech: "verb", verbTense: "perfect" }
    limit: 50
  ) {
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

| Type | Key fields |
|------|-----------|
| `Corpus` | `name`, `nodeTypes`, `featureCount`, `books` |
| `Book` | `name`, `chapters` |
| `Chapter` | `reference`, `verses` |
| `Verse` | `reference`, `text`, `words` |
| `Word` | `text`, `lemma`, `partOfSpeech`, `gloss`, `gender`, `number`, `person`, `verbStem`, `verbTense`, `feature(name)` |
| `SearchMatch` | `reference`, `text` |

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

### Claude Desktop config

Add to `~/Library/Application Support/Claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "exegia": {
      "command": "uv",
      "args": [
        "run", "--project", "/path/to/backend",
        "cf-mcp", "--corpus", "/path/to/corpus"
      ]
    }
  }
}
```

### Available tools (11)

| Category | Tool | Description |
|----------|------|-------------|
| Discovery | `list_corpora` | List loaded corpora and the active one |
| Discovery | `describe_corpus` | Node types with counts, section hierarchy |
| Discovery | `list_features` | Browse features, filter by node type |
| Discovery | `describe_feature` | Metadata + top values by frequency |
| Discovery | `get_text_formats` | Available text encodings with samples |
| Search | `search` | Pattern search — results / count / statistics / passages |
| Search | `search_continue` | Paginate large result sets via cursor |
| Search | `search_csv` | Export results to a local CSV file |
| Search | `search_syntax_guide` | Inline query syntax documentation |
| Data | `get_passages` | Retrieve text by section reference |
| Data | `get_node_features` | Batch feature lookup for a list of nodes |

### Recommended workflow for AI agents

```
describe_corpus()          → understand what node types exist
list_features()            → see what annotations are available
search_syntax_guide()      → learn the query language
search(template, "count")  → check scale before fetching results
search(template, "results") → get paginated result set
get_passages(references)   → read the matched text
```

### Programmatic use

```python
from exegia.mcp import mcp, corpus_manager

corpus_manager.load("~/.exegia/datasets/bibles/BHSA", name="BHSA")
mcp.run(transport="sse", host="localhost", port=8000)
```

---

## Corpus datasets

Datasets are Text-Fabric archives stored as zip files in Supabase Storage, extracted locally under `~/.exegia/datasets/`.

### Download a dataset

```python
from exegia.storage.dataset import DatasetStorageService
from supabase import create_client

svc = DatasetStorageService(create_client(SUPABASE_URL, SUPABASE_KEY))
await svc.download_dataset("BHSA", category="bibles")
# → ~/.exegia/datasets/bibles/BHSA/
```

### Fetch from git

```python
from exegia.corpus.fetch_from_git import fetch_datasets_from_git

paths = fetch_datasets_from_git("https://github.com/ETCBC/bhsa")
# returns list[Path] of dirs containing otext.tf + otype.tf
```

### Storage buckets

| Bucket | Content |
|--------|---------|
| `bibles` | Bible translations and critical texts (BHSA, GNT, LXX, …) |
| `lexicons` | Lexical databases |
| `dictionaries` | Language dictionaries |
| `books` | Other annotated books and commentaries |

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

## Supabase assets

Database migrations and Supabase configuration are bundled into the wheel and accessible at runtime:

```python
from exegia.supabase import migrations_dir, migration_files, config_path

# Push migrations to a Supabase project
for sql_file in migration_files():
    print(sql_file)

# Locate the bundled config.toml
print(config_path())
```

---

## Data model

The library uses three database tables:

```
library_books
  └─ book_sections   (self-referential hierarchy — unlimited depth)
       └─ book_pages (smallest addressable unit: verse, page, entry, …)
```

| Table | Purpose |
|-------|---------|
| `LibraryBook` | Catalog entry: title, author, category, source type |
| `BookSection` | Hierarchy node with `level` and `parent_uuid` |
| `BookPage` | Content unit; `section_uuid` is nullable for flat books |

**Flat book:** `LibraryBook → BookPage(s)` (no sections)

**Chaptered book:** `LibraryBook → BookSection(chapter) → BookPage(s)`

Use `BookPage.metadata` (JSON) for any corpus-specific attributes.

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

### Publish to the private registry

```bash
# Dry run (build only)
./scripts/publish.sh --dry-run

# Full publish (requires .env.publish)
cp .env.publish.example .env.publish
# fill in registry credentials
./scripts/publish.sh
```

### Project layout

```
backend/
├── main.py              # FastAPI app entry point
├── pyproject.toml       # Package config (hatchling build)
├── uv.lock
├── supabase/            # Local Supabase dev config
├── scripts/
│   └── publish.sh       # Build + publish helper
├── .github/
│   └── workflows/
│       └── publish.yml  # CI: build + publish on tag push
└── src/
    └── exegia/
        ├── auth/        # JWT + Supabase Auth
        ├── corpus/      # Git dataset fetching
        ├── graphql/     # Strawberry GraphQL schema
        ├── mcp/         # FastMCP server (cf-mcp entrypoint)
        ├── models/      # SQLAlchemy ORM models
        ├── schemas/     # Pydantic API schemas
        ├── storage/     # Supabase Storage client
        ├── supabase/    # Bundled migrations + config
        └── utils/       # EPUB/HTML → TF converters
```
