"""Local integration harness ONLY. Refuse hosted deployment until release ready.

Run from flashspace-recruitment:
uvicorn backend.workspace_local_asgi:app --host 127.0.0.1 --port 8000 --workers 1
Use a local/synthetic database, never the staging Neon connection string.
"""
import asyncio
import os
from starlette.applications import Starlette
from starlette.routing import Route, WebSocketRoute, Mount
from . import v2_stream as bridge
from .workspace_server import WorkspaceApp

async def startup():
    if os.getenv('RENDER') or os.getenv('RENDER_EXTERNAL_URL') or os.getenv('DATABASE_URL'):
        raise RuntimeError('Workspace integration harness is local-only. Release blockers must be resolved before hosted deployment.')
    bridge.backend=await asyncio.to_thread(WorkspaceApp)

app=Starlette(routes=[Route('/v2-pcm-worklet.js',bridge.pcm_worklet),WebSocketRoute('/api/v2/voice/{aid}',bridge.voice),Mount('/',app=bridge.http_app)],on_startup=[startup],on_shutdown=[bridge.shutdown])
