"""Vercel serverless entrypoint. Exposes the WSGI app defined in backend/server.py.

Vercel spins up a fresh container per invocation, so the background worker thread
started by App() would be killed before it does useful work. We disable it here;
the ClickUp sync retries still run inline on each request path that touches them.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.server import App  # noqa: E402

app = App(start_worker=False)
