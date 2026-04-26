"""
Pydantic models for the corpora API.

"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class CorpusMetadata(BaseModel):
    """Required + optional fields the Edge Function needs to convert a corpus.

    Required: name, type, language, period, repository, category[]
    Optional: description, licence, credits
    """

    model_config = ConfigDict(extra="forbid")

    name: str
    type: str
    language: str
    period: str
    repository: str
    category: list[str] = Field(min_length=1)
    description: str | None = None
    licence: str | None = None
    credits: str | None = None


class ConvertCorpusResponse(BaseModel):
    """Edge Function response — the conversion runs in the background."""

    job_id: str
    status: str
    upload_path: str


class Corpus(BaseModel):
    """Row shape returned by `SELECT * FROM public.corpora`."""

    model_config = ConfigDict(extra="ignore")

    uuid: str
    name: str
    type: str | None = None
    version: int | None = None
    format: str | None = None
    description: str | None = None
    download_uri: str | None = None
    licence: str | None = None
    date: datetime | None = None
    credits: str | None = None
    language: str
    period: str
    repository: str
    size: str | None = None
    image_url: str | None = None
    category: list[str]
    created_at: datetime
    updated_at: datetime | None = None


class ErrorResponse(BaseModel):
    error: str
