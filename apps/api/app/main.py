"""FastAPI entrypoint."""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from typing import Literal

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.catalog import autocomplete, grouped
from app.chat import handle_chat, load_draft, mark_sent
from app.db import admin_conn, reader_conn
from app.review import approve
from app.emailer import REQUIRED_SMTP, confirm_email, smtp_send
from app.ingest import load
from app.query import json_cell

log = logging.getLogger("lia")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    logging.basicConfig(level=logging.INFO)
    load()
    for _attempt in range(8):
        try:
            from app.retrieve import index_catalog

            index_catalog()
            break
        except Exception as exc:
            log.info("qdrant index not ready: %s", exc)
            import time

            time.sleep(1)
    yield


app = FastAPI(title="LIA Utilization Assistant", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class ChatIn(BaseModel):
    message: str
    persona: Literal["dean_cs", "university"]
    thread_id: str | None = None
    page: int = 1
    template_id: str | None = None


class ConfirmIn(BaseModel):
    thread_id: str = Field(min_length=1)
    confirm: bool = False


class ApproveIn(BaseModel):
    id: int
    persona: Literal["dean_cs", "university"]


@app.get("/api/health")
def health():
    try:
        with reader_conn() as conn:
            row = conn.execute("SELECT loaded_at, timetable_rows FROM data_version WHERE id = 1").fetchone()
        return {
            "status": "ok",
            "data_as_of": json_cell(row["loaded_at"]) if row else None,
            "timetable_rows": row["timetable_rows"] if row else 0,
        }
    except Exception as exc:
        return JSONResponse(status_code=503, content={"status": "error", "detail": type(exc).__name__})


@app.get("/api/templates")
def templates():
    return {"groups": grouped()}


@app.get("/api/suggest")
def suggest(q: str = ""):
    return {"groups": autocomplete(q)}


@app.post("/api/chat")
def chat(body: ChatIn):
    return handle_chat(body.message, body.persona, body.thread_id, max(1, body.page), body.template_id)


@app.post("/api/review/approve")
def approve_review(body: ApproveIn):
    if body.persona != "university":
        return JSONResponse(status_code=403, content={"ok": False, "error": "Only a university user can approve a template."})
    with admin_conn() as conn:
        result = approve(conn, body.id)
        conn.commit()
    return result


@app.post("/api/chat/confirm-email")
def confirm(body: ConfirmIn):
    try:
        env = {key: os.environ.get(key, "") for key in REQUIRED_SMTP}
        draft = load_draft(body.thread_id) if body.confirm else None

        def send(text: str) -> None:
            smtp_send(text, env)

        result = confirm_email(body.confirm is True, env, draft, send)
        if result.get("ok"):
            mark_sent(body.thread_id)
        return result
    except Exception as exc:
        log.info("email confirm failed: %s", type(exc).__name__)
        return {"ok": False, "smtp_attempted": False, "error": "Email was not sent."}
