"""Exegia — graph-based biblical and religious text study platform."""

from __future__ import annotations

import logging
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from strawberry.fastapi import GraphQLRouter

from exegia.graphql.schema import schema
from exegia.graphql.corpus import registry

__version__ = "0.1.8"

logger = logging.getLogger(__name__)


def _load_corpora_from_env() -> None:
    """Load corpora declared through env vars.

    Supported formats:
    - `EXEGIA_CORPUS=/data/BHSA` with optional `EXEGIA_CORPUS_NAME=BHSA`
    - `EXEGIA_CORPORA=BHSA=/data/BHSA,GNT=/data/GNT`
    """
    corpora = os.getenv("EXEGIA_CORPORA", "").strip()
    if corpora:
        for item in corpora.split(","):
            if not item.strip():
                continue
            if "=" not in item:
                raise ValueError(
                    "EXEGIA_CORPORA entries must be NAME=/path/to/corpus"
                )
            name, path = item.split("=", 1)
            registry.load(name.strip(), path.strip())
        return

    corpus_path = os.getenv("EXEGIA_CORPUS", "").strip()
    if not corpus_path:
        return

    corpus_name = os.getenv("EXEGIA_CORPUS_NAME", "").strip() or "default"
    registry.load(corpus_name, corpus_path)


def create_app() -> FastAPI:
    from exegia.routers.corpora import router as corpora_router  # noqa: PLC0415

    _load_corpora_from_env()

    app = FastAPI(
        title="Exegia Backend",
        version=__version__,
        docs_url="/docs",
        redoc_url=None,
    )

    cors_origins = [
        origin.strip()
        for origin in os.getenv("EXEGIA_CORS_ORIGINS", "*").split(",")
        if origin.strip()
    ]

    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins or ["*"],
        allow_credentials=False if cors_origins == ["*"] else True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health", tags=["meta"])
    def health() -> dict[str, object]:
        return {"status": "ok", "corpora": registry.names()}

    app.include_router(corpora_router)

    graphql_path = os.getenv("EXEGIA_GRAPHQL_PATH", "/graphql")
    app.include_router(GraphQLRouter(schema), prefix=graphql_path)
    return app


app = create_app()

