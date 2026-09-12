"""Staging preview entrypoint. Never provisions recruiter accounts.

Requires explicit acknowledgement of additive database initialization.
Not suitable for main/production release. Existing entrypoints are unchanged.
"""
import asyncio
import os
from starlette.applications import Starlette
from starlette.routing import Route, WebSocketRoute, Mount
from . import v2_stream as bridge
from .candidate_google import WorkspaceApp
from .v2_endpoint import EvidenceOnlyAI

STAGING_ORIGIN='https://interviewportal-sm-1.onrender.com'

def validate_staging():
    if os.getenv('RENDER_EXTERNAL_URL','').rstrip('/')!=STAGING_ORIGIN:
        raise RuntimeError('Workspace preview is restricted to the approved staging service.')
    if os.getenv('APP_ORIGIN',STAGING_ORIGIN).rstrip('/')!=STAGING_ORIGIN:
        raise RuntimeError('Workspace preview origin must match staging.')
    if not os.getenv('DATABASE_URL','').strip():
        raise RuntimeError('A backed-up staging PostgreSQL database is required.')
    if os.getenv('TEAMRECRUT_STAGING_SCHEMA_APPROVED')!='true':
        raise RuntimeError('Confirm staging backup and additive schema approval before activation.')

async def startup():
    validate_staging()
    # Uses existing AI environment configuration; does not fetch or create keys.
    bridge.backend=await asyncio.to_thread(WorkspaceApp,ai=EvidenceOnlyAI())

app=Starlette(routes=[Route('/v2-pcm-worklet.js',bridge.pcm_worklet),
    WebSocketRoute('/api/v2/voice/{aid}',bridge.voice),Mount('/',app=bridge.http_app)],
    on_startup=[startup],on_shutdown=[bridge.shutdown])
