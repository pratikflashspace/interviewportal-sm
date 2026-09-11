"""Isolated integration runtime; existing deployed entrypoints remain unchanged."""
import asyncio
from starlette.applications import Starlette
from starlette.routing import Route,WebSocketRoute,Mount
from . import v2_stream as bridge
from .integrated_recordings import create_app

async def startup():bridge.backend=await asyncio.to_thread(create_app)

app=Starlette(routes=[Route('/v2-pcm-worklet.js',bridge.pcm_worklet),
    WebSocketRoute('/api/v2/voice/{aid}',bridge.voice),Mount('/',app=bridge.http_app)],
    on_startup=[startup],on_shutdown=[bridge.shutdown])
