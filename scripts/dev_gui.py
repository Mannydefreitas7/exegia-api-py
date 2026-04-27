#!/usr/bin/env python
"""
Dev GUI for testing Exegia corpora API endpoints.

Tabs:
  - List Corpora  → GET /api/corpora (filterable, paginated table)
  - Get Corpus    → GET /api/corpora/{name}
  - Upload        → POST /api/corpora/convert (multipart → Edge Function)

Run:
    uv run Python scripts/dev_gui.py
    uv run Python scripts/dev_gui.py --base-url http://localhost:8000
"""

from __future__ import annotations

import asyncio
import json
import sys
from typing import Any

import httpx
from nicegui import events, ui

_state: dict[str, Any] = {"base_url": "http://localhost:8000"}


# ── HTTP helpers ──────────────────────────────────────────────────────────────


async def _get(path: str, **params: Any) -> tuple[int, Any]:
    clean = {k: v for k, v in params.items() if v is not None and v != ""}
    try:
        async with httpx.AsyncClient(base_url=_state["base_url"], timeout=10) as c:
            r = await c.get(path, params=clean)
        try:
            return r.status_code, r.json()
        except Exception:
            return r.status_code, r.text
    except httpx.ConnectError:
        return 0, f"Cannot connect to {_state['base_url']} — is the API server running?"
    except httpx.ReadTimeout:
        return 0, f"Request timed out — {_state['base_url']}{path}"
    except Exception as exc:
        return 0, f"Network error: {exc}"


async def _post_multipart(
    path: str,
    data: dict[str, Any],
    file_name: str,
    file_bytes: bytes,
    mime: str,
) -> tuple[int, Any]:
    try:
        async with httpx.AsyncClient(base_url=_state["base_url"], timeout=60) as c:
            files = {"file": (file_name, file_bytes, mime)}
            r = await c.post(path, data=data, files=files)
        try:
            return r.status_code, r.json()
        except Exception:
            return r.status_code, r.text
    except httpx.ConnectError:
        return 0, f"Cannot connect to {_state['base_url']} — is the API server running?"
    except httpx.ReadTimeout:
        return 0, f"Request timed out uploading to {_state['base_url']}{path}"
    except Exception as exc:
        return 0, f"Network error: {exc}"


def _json_display(parent: ui.card, code: int, body: Any) -> None:
    """Render a status badge + formatted JSON inside a card."""
    if code == 0:
        color = "warning"
        label = "Unreachable"
    elif code < 400:
        color = "positive"
        label = f"HTTP {code}"
    else:
        color = "negative"
        label = f"HTTP {code}"
    with parent:
        ui.badge(label, color=color).classes("text-sm mb-2")
        if isinstance(body, str):
            ui.label(body).classes("text-sm text-gray-600")
        else:
            ui.code(json.dumps(body, indent=2, default=str)).classes("w-full text-xs")


# ── List Corpora tab ──────────────────────────────────────────────────────────

COLUMNS = [
    {
        "name": "name",
        "label": "Name",
        "field": "name",
        "sortable": True,
        "align": "left",
    },
    {
        "name": "language",
        "label": "Lang",
        "field": "language",
        "sortable": True,
        "align": "left",
    },
    {
        "name": "type",
        "label": "Type",
        "field": "type",
        "sortable": True,
        "align": "left",
    },
    {"name": "period", "label": "Period", "field": "period", "align": "left"},
    {"name": "category", "label": "Category", "field": "category", "align": "left"},
    {"name": "version", "label": "Ver", "field": "version", "align": "right"},
    {
        "name": "created_at",
        "label": "Created",
        "field": "created_at",
        "sortable": True,
        "align": "left",
    },
]


def _build_list_tab() -> None:
    with ui.row().classes("w-full gap-3 items-end flex-wrap mb-2"):
        lang = (
            ui.input("Language", placeholder="grc / hbo")
            .props("dense outlined clearable")
            .classes("w-32")
        )
        typ = (
            ui.input("Type", placeholder="text")
            .props("dense outlined clearable")
            .classes("w-28")
        )
        limit = (
            ui.number("Limit", value=50, min=1, max=200)
            .props("dense outlined")
            .classes("w-20")
        )
        offset = (
            ui.number("Offset", value=0, min=0).props("dense outlined").classes("w-20")
        )
        refresh_btn = ui.button("Refresh", icon="refresh").props("flat color=indigo")

    table = (
        ui.table(columns=COLUMNS, rows=[], row_key="uuid")
        .classes("w-full")
        .props("dense")
    )
    table.add_slot(
        "body-cell-name",
        '<q-td :props="props">'
        '<span class="font-mono text-indigo-700 font-semibold">{{ props.value }}</span>'
        "</q-td>",
    )
    status_lbl = ui.label("").classes("text-xs text-gray-400 mt-1")

    async def refresh() -> None:
        refresh_btn.props("loading")
        status_lbl.text = "Loading…"
        code, data = await _get(
            "/api/corpora",
            language=lang.value or None,
            type=typ.value or None,
            limit=int(limit.value or 50),
            offset=int(offset.value or 0),
        )
        refresh_btn.props(remove="loading")
        if code == 200:
            rows = [{**c, "category": ", ".join(c.get("category") or [])} for c in data]
            table.rows = rows
            status_lbl.text = f"{len(rows)} corpus(es) returned"
        elif code == 0:
            ui.notify(str(data), type="warning")
            status_lbl.text = str(data)
        else:
            ui.notify(f"Error {code}: {data}", type="negative")
            status_lbl.text = f"Error {code}"

    refresh_btn.on("click", lambda: asyncio.ensure_future(refresh()))
    ui.timer(0.1, refresh, once=True)


# ── Get Corpus tab ────────────────────────────────────────────────────────────


def _build_get_tab() -> None:
    with ui.row().classes("w-full gap-3 items-end mb-2"):
        name_in = (
            ui.input("Corpus name", placeholder="bhsa")
            .props("dense outlined")
            .classes("flex-1")
        )
        fetch_btn = ui.button("Fetch", icon="search").props("color=indigo")

    result_card = ui.card().classes("w-full hidden")

    async def fetch() -> None:
        n = name_in.value.strip()
        if not n:
            ui.notify("Enter a corpus name", type="warning")
            return
        fetch_btn.props("loading")
        code, data = await _get(f"/api/corpora/{n}")
        fetch_btn.props(remove="loading")
        result_card.clear()
        result_card.classes(remove="hidden")
        _json_display(result_card, code, data)

    fetch_btn.on("click", lambda: asyncio.ensure_future(fetch()))
    name_in.on("keydown.enter", lambda: asyncio.ensure_future(fetch()))


# ── Upload tab ────────────────────────────────────────────────────────────────


def _build_upload_tab() -> None:
    _file: dict[str, Any] = {}

    with ui.card().classes("w-full"):
        ui.label("Convert & upload corpus").classes("text-lg font-semibold mb-3")

        with ui.grid(columns=2).classes("w-full gap-x-4 gap-y-2"):
            name_in = (
                ui.input("Name *", placeholder="bhsa")
                .props("dense outlined")
                .classes("w-full")
            )
            type_in = (
                ui.input("Type *", placeholder="text")
                .props("dense outlined")
                .classes("w-full")
            )
            lang_in = (
                ui.input("Language *", placeholder="hbo")
                .props("dense outlined")
                .classes("w-full")
            )
            period_in = (
                ui.input("Period *", placeholder="ancient")
                .props("dense outlined")
                .classes("w-full")
            )

        repo_in = (
            ui.input("Repository *", placeholder="https://github.com/ETCBC/bhsa")
            .props("dense outlined")
            .classes("w-full mt-2")
        )
        cat_in = (
            ui.input("Category * (comma-separated)", placeholder="bible, ot")
            .props("dense outlined")
            .classes("w-full mt-1")
        )

        with ui.expansion("Optional fields", icon="expand_more").classes("w-full mt-2"):
            desc_in = ui.textarea("Description").props("outlined").classes("w-full")
            with ui.row().classes("w-full gap-3 mt-1"):
                lic_in = ui.input("Licence").props("dense outlined").classes("flex-1")
                cred_in = ui.input("Credits").props("dense outlined").classes("flex-1")

        file_lbl = ui.label("No file selected").classes("text-xs text-gray-400 mt-3")

        def on_upload(e: events.UploadEventArguments) -> None:
            _file["name"] = e.name
            _file["bytes"] = e.content.read()
            _file["mime"] = e.type or "application/zip"
            size_kb = len(_file["bytes"]) / 1024
            file_lbl.text = f"Ready: {e.name} ({size_kb:,.1f} KB)"
            ui.notify(f"File ready: {e.name}", type="positive")

        ui.upload(
            label="Corpus archive (.zip)",
            on_upload=on_upload,
            max_file_size=500_000_000,
            auto_upload=True,
        ).props("accept=.zip flat bordered").classes("w-full mt-1")

    result_card = ui.card().classes("w-full mt-3 hidden")

    async def submit() -> None:
        required = [
            name_in.value,
            type_in.value,
            lang_in.value,
            period_in.value,
            repo_in.value,
            cat_in.value,
        ]
        if not all(required):
            ui.notify("Fill in all required (*) fields", type="warning")
            return
        if not _file:
            ui.notify("Upload a .zip file first", type="warning")
            return

        cats = [c.strip() for c in cat_in.value.split(",") if c.strip()]
        form: dict[str, Any] = {
            "name": name_in.value.strip(),
            "type": type_in.value.strip(),
            "language": lang_in.value.strip(),
            "period": period_in.value.strip(),
            "repository": repo_in.value.strip(),
            "category": cats,
        }
        if desc_in.value:
            form["description"] = desc_in.value
        if lic_in.value:
            form["licence"] = lic_in.value
        if cred_in.value:
            form["credits"] = cred_in.value

        submit_btn.props("loading")
        code, resp = await _post_multipart(
            "/api/corpora/convert",
            data=form,
            file_name=_file["name"],
            file_bytes=_file["bytes"],
            mime=_file["mime"],
        )
        submit_btn.props(remove="loading")

        result_card.clear()
        result_card.classes(remove="hidden")
        if code in (200, 202):
            ui.notify("Corpus conversion started!", type="positive")
            with result_card:
                ui.badge(f"HTTP {code}", color="positive").classes("mb-2")
                with ui.row().classes("gap-4 flex-wrap"):
                    for key, val in resp.items():
                        with ui.card().tight().classes("p-3 bg-gray-50"):
                            ui.label(key).classes(
                                "text-xs text-gray-500 uppercase tracking-wide"
                            )
                            ui.label(str(val)).classes(
                                "font-mono font-medium text-sm mt-1"
                            )
        else:
            ui.notify(f"Error {code}", type="negative")
            _json_display(result_card, code, resp)

    submit_btn = ui.button(
        "Submit", icon="cloud_upload", on_click=lambda: asyncio.ensure_future(submit())
    ).classes("mt-3")


# ── Page ──────────────────────────────────────────────────────────────────────


@ui.page("/")
def index() -> None:
    ui.query("body").style("background: #f8fafc")

    with ui.header().classes(
        "bg-indigo-700 text-white flex items-center gap-3 px-6 py-3 shadow-md"
    ):
        ui.icon("menu_book", size="2rem")
        ui.label("Exegia Corpus Dev GUI").classes("text-xl font-semibold flex-1")
        url_in = (
            ui.input(value=_state["base_url"])
            .props("dense dark outlined label='API Base URL'")
            .classes("w-80 text-sm")
        )
        url_in.on(
            "change", lambda e: _state.update(base_url=str(e.value or "").rstrip("/"))
        )

    with ui.tabs().classes("w-full bg-white shadow-sm") as tabs:
        t_list = ui.tab("list", label="List Corpora", icon="list")
        t_get = ui.tab("get", label="Get Corpus", icon="search")
        t_upload = ui.tab("upload", label="Upload", icon="cloud_upload")

    with ui.tab_panels(tabs, value=t_list).classes("w-full"):
        with ui.tab_panel(t_list).classes("p-4"):
            _build_list_tab()
        with ui.tab_panel(t_get).classes("p-4"):
            _build_get_tab()
        with ui.tab_panel(t_upload).classes("p-4"):
            _build_upload_tab()


if __name__ in {"__main__", "__mp_main__"}:
    if "--base-url" in sys.argv:
        idx = sys.argv.index("--base-url")
        if idx + 1 < len(sys.argv):
            _state["base_url"] = sys.argv[idx + 1].rstrip("/")

    ui.run(title="Exegia Dev GUI", port=8080, reload=False, favicon="📚")
