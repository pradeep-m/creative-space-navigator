"""Vercel serverless entrypoint.

The catch-all route in vercel.json sends every request to this function, which loses the
original path. The route passes it along as a __vpath query parameter and this wrapper
restores it into the ASGI scope before handing off to FastAPI. Note that `$1` is only
interpolated by the legacy `routes` key; it is passed through literally under `rewrites`.

When __vpath is absent the scope is left untouched, so running the app directly under
uvicorn behaves normally.
"""

import sys
from pathlib import Path
from urllib.parse import parse_qsl, urlencode

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import app as fastapi_app  # noqa: E402


async def app(scope, receive, send):
    if scope["type"] == "http":
        original = None
        passthrough = []
        for key, value in parse_qsl(
            scope.get("query_string", b"").decode(), keep_blank_values=True
        ):
            if key == "__vpath" and original is None:
                original = value
            else:
                passthrough.append((key, value))

        if original:
            if not original.startswith("/"):
                original = "/" + original
            scope = {
                **scope,
                "path": original,
                "raw_path": original.encode(),
                "query_string": urlencode(passthrough).encode(),
            }

    await fastapi_app(scope, receive, send)
