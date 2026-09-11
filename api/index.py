"""Vercel serverless entrypoint. Exposes the FastAPI app from the repo root."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import app  # noqa: E402

__all__ = ["app"]
