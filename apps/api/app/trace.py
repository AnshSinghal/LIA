"""Local JSON trace, plus Langfuse only when its keys are present."""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone

from app.config import trace_dir

log = logging.getLogger("lia.trace")


def record_trace(payload: dict) -> None:
    body = {"ts": datetime.now(timezone.utc).isoformat(), **payload}
    path = trace_dir() / "turns.jsonl"
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(body, default=str) + "\n")
    _langfuse(body)


def _langfuse(body: dict) -> None:
    public = os.environ.get("LANGFUSE_PUBLIC_KEY")
    secret = os.environ.get("LANGFUSE_SECRET_KEY")
    if not public or not secret:
        return
    try:
        from langfuse import Langfuse

        client = Langfuse(public_key=public, secret_key=secret, host=os.environ.get("LANGFUSE_HOST") or None)
        client.trace(name="lia-chat", input={"persona": body.get("persona")}, output={"route": body.get("route")}, metadata=body)
    except Exception as exc:
        log.info("langfuse skipped: %s", exc)
