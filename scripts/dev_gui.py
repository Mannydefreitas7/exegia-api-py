#!/usr/bin/env python
"""Dev GUI for testing Exegia corpora API endpoints.

Tabs:
  - List Corpora  → GET /api/corpora (filterable, paginated table)
  - Get Corpus    → GET /api/corpora/{name}
  - Upload        → POST /api/corpora/convert (multipart → Edge Function)

Run:
    uv run python scripts/dev_gui.py
    uv run python scripts/dev_gui.py --base-url http://localhost:8000
"""

from __future__ import annotations

import json
import sys
from typing import Any

import httpx
from fasthtml.common import (
    A,
    Code,
    Div,
    Li,
    Main,
    P,
    Pre,
    Span,
    Title,
    Ul,
    UploadFile,
    serve,
)
from monsterui.all import (
    H3,
    Button,
    ButtonT,
    Card,
    Details,
    DivFullySpaced,
    DivHStacked,
    Form,
    Grid,
    Input,
    Label,
    LabelInput,
    Summary,
    TableFromLists,
    TableT,
    Theme,
    fast_app,
)
from monsterui.franken import H2

_DEFAULT_BASE_URL = "http://127.0.0.1:54321"

if "--base-url" in sys.argv:
    _idx = sys.argv.index("--base-url")
    if _idx + 1 < len(sys.argv):
        _DEFAULT_BASE_URL = sys.argv[_idx + 1].rstrip("/")


app, rt = fast_app(
    hdrs=(Theme.neutral.headers()),
    secret_key="exegia-dev-gui-2024",
    pico=False,
    live=True,
)


# ── HTTP helpers ──────────────────────────────────────────────────────────────


async def _get(base_url: str, path: str, **params: Any) -> tuple[int, Any]:
    clean = {k: v for k, v in params.items() if v is not None and v != ""}
    try:
        async with httpx.AsyncClient(base_url=base_url, timeout=10) as c:
            r = await c.get(path, params=clean)
        try:
            return r.status_code, r.json()
        except Exception:
            return r.status_code, r.text
    except httpx.ConnectError:
        return 0, f"Cannot connect to {base_url} — is the API server running?"
    except httpx.ReadTimeout:
        return 0, f"Request timed out — {base_url}{path}"
    except Exception as exc:
        return 0, f"Network error: {exc}"


async def _post_multipart(
    base_url: str,
    path: str,
    data: dict[str, Any],
    file_name: str,
    file_bytes: bytes,
    mime: str,
) -> tuple[int, Any]:
    try:
        async with httpx.AsyncClient(base_url=base_url, timeout=60) as c:
            r = await c.post(
                path, data=data, files={"file": (file_name, file_bytes, mime)}
            )
        try:
            return r.status_code, r.json()
        except Exception:
            return r.status_code, r.text
    except httpx.ConnectError:
        return 0, f"Cannot connect to {base_url} — is the API server running?"
    except httpx.ReadTimeout:
        return 0, f"Request timed out uploading to {base_url}{path}"
    except Exception as exc:
        return 0, f"Network error: {exc}"


# ── UI helpers ────────────────────────────────────────────────────────────────


def _result_view(code: int, body: Any):
    if code == 0:
        badge_cls, label = "bg-yellow-100 text-yellow-800", "Unreachable"
    elif code < 400:
        badge_cls, label = "bg-green-100 text-green-800", f"HTTP {code}"
    else:
        badge_cls, label = "bg-red-100 text-red-800", f"HTTP {code}"
    text = body if isinstance(body, str) else json.dumps(body, indent=2, default=str)
    return Div(
        Span(
            label,
            cls=f"inline-block text-xs font-semibold px-2 py-1 rounded mb-2 {badge_cls}",
        ),
        Pre(
            Code(text),
            cls="text-xs overflow-auto bg-neutral-50 dark:bg-neutral-900 p-3 rounded border border-neutral-200 dark:border-neutral-700",
        ),
    )


# ── Tab nav ───────────────────────────────────────────────────────────────────

_TABS = [("list", "List Corpora"), ("get", "Get Corpus"), ("upload", "Upload")]


def _tab_nav(active: str, oob: bool = False):
    items = []
    for key, label in _TABS:
        link_cls = (
            "block px-4 py-2 text-sm font-medium border-b-2 cursor-pointer transition-colors "
            + (
                "border-neutral-900 text-neutral-900 dark:border-neutral-100 dark:text-neutral-100"
                if key == active
                else "border-transparent text-neutral-500 hover:text-neutral-700 hover:border-neutral-300 dark:hover:text-neutral-300 dark:hover:border-neutral-600"
            )
        )
        items.append(
            Li(
                A(
                    label,
                    cls=link_cls,
                    hx_get=f"/tab/{key}",
                    hx_target="#tab-content",
                    hx_swap="innerHTML",
                )
            )
        )
    kw: dict[str, Any] = {
        "id": "tab-nav",
        "cls": "flex border-b border-neutral-200 dark:border-neutral-700 mb-4",
    }
    if oob:
        kw["hx_swap_oob"] = "true"
    return Ul(*items, **kw)


@rt("/tab/{key}")
def tab_page(key: str):
    fn = {"list": _list_tab, "get": _get_tab, "upload": _upload_tab}.get(key, _list_tab)
    return _tab_nav(key, oob=True), fn()


# ── List Corpora tab ──────────────────────────────────────────────────────────


def _list_tab():
    return Div(
        Form(
            DivHStacked(
                Input(name="language", placeholder="grc / hbo", cls="w-28"),
                Input(name="type", placeholder="text", cls="w-24"),
                Input(
                    name="limit",
                    type="number",
                    value="50",
                    min="1",
                    max="200",
                    cls="w-20",
                ),
                Input(name="offset", type="number", value="0", min="0", cls="w-20"),
                Button("Refresh", cls=ButtonT.default),
                cls="gap-3 items-end flex-wrap mb-3",
            ),
            hx_get="/list-results",
            hx_target="#list-table",
            hx_swap="innerHTML",
            hx_trigger="submit, load",
        ),
        P("", id="list-status", cls="text-xs text-neutral-400 mb-2"),
        Div(id="list-table"),
    )


@rt("/list-results")
async def list_results(
    sess, language: str = "", type: str = "", limit: int = 50, offset: int = 0
):
    base_url = sess.get("base_url", _DEFAULT_BASE_URL)
    code, data = await _get(
        base_url,
        "/api/corpora",
        language=language or None,
        type=type or None,
        limit=limit,
        offset=offset,
    )
    if code == 200:
        rows = [{**c, "category": ", ".join(c.get("category") or [])} for c in data]
        fields = [
            "name",
            "language",
            "type",
            "period",
            "category",
            "version",
            "created_at",
        ]
        headers = ["Name", "Lang", "Type", "Period", "Category", "Ver", "Created"]
        body = [[str(r.get(f, "")) for f in fields] for r in rows]
        return (
            P(
                f"{len(rows)} corpus(es) returned",
                id="list-status",
                hx_swap_oob="true",
                cls="text-xs text-neutral-400 mb-2",
            ),
            TableFromLists(
                headers, body, cls=TableT.hover + TableT.divider + TableT.sm
            ),
        )
    else:
        return (
            P(
                f"Error {code}" if code else str(data)[:80],
                id="list-status",
                hx_swap_oob="true",
                cls="text-xs text-red-400 mb-2",
            ),
            _result_view(code, data),
        )


# ── Get Corpus tab ────────────────────────────────────────────────────────────


def _get_tab():
    return Div(
        Form(
            DivHStacked(
                Input(name="name", placeholder="bhsa", cls="flex-1"),
                Button("Fetch", cls=ButtonT.default),
                cls="gap-3 items-end mb-3",
            ),
            hx_get="/get-result",
            hx_target="#get-result",
            hx_swap="innerHTML",
        ),
        Div(id="get-result"),
    )


@rt("/get-result")
async def get_result(sess, name: str = ""):
    if not name.strip():
        return P("Enter a corpus name", cls="text-sm text-yellow-600")
    base_url = sess.get("base_url", _DEFAULT_BASE_URL)
    code, data = await _get(base_url, f"/api/corpora/{name.strip()}")
    return _result_view(code, data)


# ── Upload tab ────────────────────────────────────────────────────────────────


def _upload_tab():
    return Div(
        Form(
            Card(
                H3("Convert & upload corpus", cls="text-lg font-semibold mb-4"),
                Grid(
                    LabelInput("Name", id="name", placeholder="bhsa"),
                    LabelInput("Type", id="type", placeholder="text"),
                    LabelInput("Language", id="language", placeholder="hbo"),
                    LabelInput("Period", id="period", placeholder="ancient"),
                    cols=2,
                    cls="gap-4 mb-2",
                ),
                LabelInput(
                    "Repository",
                    id="repository",
                    placeholder="https://github.com/ETCBC/bhsa",
                    cls="mb-1",
                ),
                LabelInput(
                    "Category (comma-separated)",
                    id="category",
                    placeholder="bible, ot",
                    cls="mb-2",
                ),
                Details(
                    Summary(
                        "Optional fields",
                        cls="text-sm text-neutral-500 cursor-pointer mb-2",
                    ),
                    Div(
                        LabelInput("Description", id="description"),
                        DivHStacked(
                            LabelInput("Licence", id="licence", cls="flex-1"),
                            LabelInput("Credits", id="credits", cls="flex-1"),
                            cls="gap-3 mt-1",
                        ),
                        cls="mt-2 space-y-2",
                    ),
                    cls="mt-2",
                ),
                Div(
                    Label("Corpus archive (.zip)", cls="text-sm font-medium"),
                    Input(
                        type="file", name="file", accept=".zip", cls="mt-1 block w-full"
                    ),
                    cls="mt-3",
                ),
            ),
            Button("Submit", cls=ButtonT.primary, type="submit"),
            hx_post="/upload-result",
            hx_target="#upload-result",
            hx_swap="innerHTML",
            enctype="multipart/form-data",
            cls="space-y-3",
        ),
        Div(id="upload-result", cls="mt-3"),
    )


@rt("/upload-result")
async def upload_result(
    sess,
    file: UploadFile,
    name: str = "",
    type: str = "",
    language: str = "",
    period: str = "",
    repository: str = "",
    category: str = "",
    description: str = "",
    licence: str = "",
    credits: str = "",
):
    # if not all(f.strip() for f in [name, type, language, period, repository, category]):
    #     return P("Fill in all required (*) fields", cls="text-red-600 text-sm")
    if not file or not file.filename:
        return P("Upload a .zip file first", cls="text-yellow-600 text-sm")

    file_bytes = await file.read()
    form_data: dict[str, Any] = {
        "name": name.strip(),
        "type": type.strip(),
        "language": language.strip(),
        "period": period.strip(),
        "repository": repository.strip(),
        "category": [c.strip() for c in category.split(",") if c.strip()],
    }
    if description:
        form_data["description"] = description
    if licence:
        form_data["licence"] = licence
    if credits:
        form_data["credits"] = credits

    base_url = sess.get("base_url", _DEFAULT_BASE_URL)
    code, resp = await _post_multipart(
        base_url,
        "/api/corpora/convert",
        data=form_data,
        file_name=file.filename,
        file_bytes=file_bytes,
        mime=file.content_type or "application/zip",
    )
    return _result_view(code, resp)


# ── Main page ─────────────────────────────────────────────────────────────────


@rt("/")
def index(sess):
    base_url = sess.get("base_url", _DEFAULT_BASE_URL)
    return Title("Exegia Dev GUI"), Main(
        Div(
            DivFullySpaced(
                DivHStacked(
                    Span("📚", cls="text-2xl"),
                    H2("Exegia Corpus Dev GUI", cls="text-xl font-semibold text-white"),
                    cls="gap-3 items-center",
                ),
                Form(
                    Input(
                        name="base_url",
                        value=base_url,
                        placeholder="http://localhost:8000",
                        cls="w-80 text-sm bg-neutral-800 text-white border-neutral-600 rounded px-3 py-1",
                    ),
                    hx_post="/set-base-url",
                    hx_trigger="change from:input",
                    hx_swap="none",
                ),
            ),
            cls="bg-neutral-950 px-6 py-3",
        ),
        Div(
            _tab_nav("list"),
            Div(_list_tab(), id="tab-content"),
            cls="p-4",
        ),
        cls="min-h-screen bg-neutral-50 dark:bg-neutral-950",
    )


@rt("/set-base-url")
def set_base_url(sess, base_url: str = ""):
    sess["base_url"] = (base_url or _DEFAULT_BASE_URL).rstrip("/")


serve(port=8080, reload=True)
