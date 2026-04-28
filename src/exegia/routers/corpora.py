"""
Routes that proxy `convert-corpus` and expose the `public.corpora` table.

Endpoints:
- POST /api/corpora/convert  -> forwards multipart upload to Edge Function
- GET  /api/corpora          -> list rows (paginated)
- GET  /api/corpora/{name}   -> fetch a single corpus by unique name
"""

from __future__ import annotations

import asyncio
import logging
from typing import Annotated

import httpx
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from postgrest.exceptions import APIError
from supabase import Client

from exegia.schemas import ConvertCorpusResponse, Corpus, CorpusMetadata
from exegia.utils.connect import get_anon_client, get_service_client
from scripts.config import Settings, get_settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/corpora", tags=["corpora"])

# How long to wait on the Edge Function. The function returns 202 quickly
# (the heavy lifting is in `EdgeRuntime.waitUntil`), so a short timeout is fine.
EDGE_FUNCTION_TIMEOUT_S = 30.0


# ── Dependencies ────────────────────────────────────────────────────────────


def _settings() -> Settings:
    return get_settings()


def _anon_client() -> Client:
    return get_anon_client()


def _service_client() -> Client:
    return get_service_client()


# ── POST /api/corpora/convert ───────────────────────────────────────────────


@router.post(
    "/convert",
    response_model=ConvertCorpusResponse,
    status_code=202,
    summary="Convert a corpus archive via the convert-corpus Edge Function",
)
async def convert_corpus(
    settings: Annotated[Settings, Depends(_settings)],
    file: Annotated[UploadFile, File(description="Source corpus archive (.zip)")],
    name: Annotated[str, Form()],
    type: Annotated[str, Form()],
    language: Annotated[str, Form()],
    period: Annotated[str, Form()],
    repository: Annotated[str, Form()],
    category: Annotated[list[str], Form(min_length=1)],
    description: Annotated[str | None, Form()] = None,
    licence: Annotated[str | None, Form()] = None,
    credits: Annotated[str | None, Form()] = None,
) -> ConvertCorpusResponse:
    """Forward a multipart/form-data upload to the local Edge Function.

    The Edge Function is invoked with the service-role key so it can bypass
    RLS for the storage upload + database insert. We avoid the supabase-py
    `functions.invoke()` helper because it can't stream multipart bodies
    cleanly; httpx forwards the upload bytes verbatim.
    """
    if not file.filename or not file.filename.lower().endswith(".zip"):
        raise HTTPException(status_code=400, detail="file must be a .zip")
    if not settings.supabase_service_role_key:
        raise HTTPException(
            status_code=500,
            detail="SUPABASE_SERVICE_ROLE_KEY is not configured on the server",
        )

    # Validate metadata server-side so we can return a clean 422 instead of
    # bubbling a 400 from the Edge Function.
    metadata = CorpusMetadata(
        name=name,
        type=type,
        language=language,
        period=period,
        repository=repository,
        category=category,
        description=description,
        licence=licence,
        credits=credits,
    )

    function_url = (
        f"{settings.supabase_url.rstrip('/')}/functions/v1/"
        f"{settings.convert_corpus_function}"
    )

    # Repackage the form-data for the Edge Function. We can't blindly forward
    # the original request body because Starlette has already consumed it.
    # NOTE: httpx wants `data` as a dict (with list values for repeated keys),
    # not a list of tuples — passing tuples crashes the multipart encoder.
    files = {
        "file": (
            file.filename,
            await file.read(),
            file.content_type or "application/zip",
        )
    }
    data: dict[str, str | list[str]] = {
        "name": metadata.name,
        "type": metadata.type,
        "language": metadata.language,
        "period": metadata.period,
        "repository": metadata.repository,
        "category": list(metadata.category),
    }
    if metadata.description is not None:
        data["description"] = metadata.description
    if metadata.licence is not None:
        data["licence"] = metadata.licence
    if metadata.credits is not None:
        data["credits"] = metadata.credits

    headers = {
        "Authorization": f"Bearer {settings.supabase_service_role_key}",
        # The Edge Function reads the project URL/key from its own env, so
        # we just need the auth + apikey envelope here.
        "apikey": settings.supabase_service_role_key,
    }

    def _post_sync() -> httpx.Response:
        # NOTE: we use the sync httpx.Client here on purpose. httpx 0.28.x
        # has a known incompatibility where building a request with `files=`
        # on AsyncClient produces a sync stream and raises
        # "Attempted to send an sync request with an AsyncClient instance."
        # Running the sync call in a worker thread avoids that bug entirely
        # and is just as performant for the small forwarded payload.
        with httpx.Client(timeout=EDGE_FUNCTION_TIMEOUT_S) as client:
            return client.post(function_url, headers=headers, data=data, files=files)

    try:
        response = await asyncio.to_thread(_post_sync)
    except httpx.HTTPError as exc:
        logger.error(
            "convert-corpus upstream failed",
            extra={"url": function_url, "error": str(exc)},
        )
        raise HTTPException(
            status_code=502, detail=f"Edge Function unreachable: {exc}"
        ) from exc

    if response.status_code >= 400:
        # Surface the Edge Function's own error payload when possible.
        try:
            payload = response.json()
        except ValueError:
            payload = {"error": response.text}
        raise HTTPException(status_code=response.status_code, detail=payload)

    try:
        body = response.json()
    except ValueError as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Edge Function returned non-JSON response: {response.text[:200]}",
        ) from exc

    return ConvertCorpusResponse(**body)


# ── GET /api/corpora ─────────────────────────────────────────────────────────


@router.get("", response_model=list[Corpus], summary="List corpora")
def list_corpora(
    supabase: Annotated[Client, Depends(_anon_client)],
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    language: str | None = None,
    type_: Annotated[str | None, Query(alias="type")] = None,
) -> list[Corpus]:
    """Return rows from `public.corpora`, optionally filtered."""
    query = supabase.table("corpora").select("*")

    if language is not None:
        query = query.eq("language", language)
    if type_ is not None:
        query = query.eq("type", type_)

    try:
        response = (
            query.order("created_at", desc=True)
            .range(offset, offset + limit - 1)
            .execute()
        )
    except APIError as exc:
        logger.error("corpora list query failed: %s", exc)
        raise HTTPException(
            status_code=502, detail={"error": "upstream", "message": exc.message}
        ) from exc
    return [Corpus(**row) for row in response.data]


# ── GET /api/corpora/{name} ──────────────────────────────────────────────────


@router.get(
    "/{name}",
    response_model=Corpus,
    summary="Fetch a single corpus by its unique name",
)
def get_corpus(
    name: str,
    supabase: Annotated[Client, Depends(_anon_client)],
) -> Corpus:
    try:
        response = (
            supabase.table("corpora")
            .select("*")
            .eq("name", name)
            .maybe_single()
            .execute()
        )
    except APIError as exc:
        logger.error("corpora get query failed: %s", exc)
        raise HTTPException(
            status_code=502, detail={"error": "upstream", "message": exc.message}
        ) from exc
    if response is None or not response.data:
        raise HTTPException(status_code=404, detail=f"corpus '{name}' not found")
    return Corpus(**response.data)
