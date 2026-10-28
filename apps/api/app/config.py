"""Paths and environment helpers."""

from __future__ import annotations

import os
from pathlib import Path


def data_dir() -> Path:
    raw = os.environ.get("DATA_DIR")
    if raw:
        return Path(raw)
    for parent in Path(__file__).resolve().parents:
        candidate = parent / "docs" / "tech - assignment"
        if candidate.is_dir():
            return candidate
    raise FileNotFoundError("Set DATA_DIR to the folder that contains the Excel extracts")


def trace_dir() -> Path:
    path = Path(os.environ.get("TRACE_DIR", "var/traces"))
    path.mkdir(parents=True, exist_ok=True)
    return path


def admin_dsn() -> str:
    return os.environ.get("DATABASE_URL", "postgresql://lia:lia@localhost:5432/lia")


def reader_dsn() -> str:
    return os.environ.get("READONLY_DATABASE_URL", "postgresql://lia_reader:lia_reader@localhost:5432/lia")


def reader_password() -> str:
    password = os.environ.get("READONLY_PASSWORD", "lia_reader")
    if not password.replace("_", "").isalnum():
        raise RuntimeError("READONLY_PASSWORD must be alphanumeric")
    return password
