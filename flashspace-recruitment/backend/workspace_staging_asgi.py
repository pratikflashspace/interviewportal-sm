"""Staging preview entrypoint. Never provisions recruiter accounts.

Requires explicit acknowledgement of additive database initialization.
Not suitable for main/production release. Existing entrypoints are unchanged.
"""
import asyncio
import os
from starlette.applications import Starlette
from starlette.routing import Route, WebSocketRoute, Mount
from . import v2_stream as bridge
from .candidate_account import WorkspaceApp

RENDER_SERVICE_ORIGIN='https://interviewportal-sm-1.onrender.com'
# Backwards-compatible alias: the original single-origin name.
STAGING_ORIGIN=RENDER_SERVICE_ORIGIN
# Public front-ends for this service. The custom domain is served alongside the
# Render URL; both are valid same-origin hosts for candidates.
PUBLIC_ORIGINS={
    RENDER_SERVICE_ORIGIN,
    'https://recrut.teamlens.co',
}

def validate_staging():
    if os.getenv('RENDER_EXTERNAL_URL','').rstrip('/')!=RENDER_SERVICE_ORIGIN:
        raise RuntimeError('Workspace preview is restricted to the approved staging service.')
    if os.getenv('APP_ORIGIN',RENDER_SERVICE_ORIGIN).rstrip('/') not in PUBLIC_ORIGINS:
        raise RuntimeError('Workspace preview origin must match a public front-end of this service.')
    if not os.getenv('DATABASE_URL','').strip():
        raise RuntimeError('A backed-up staging PostgreSQL database is required.')
    if os.getenv('TEAMRECRUT_STAGING_SCHEMA_APPROVED')!='true':
        raise RuntimeError('Confirm staging backup and additive schema approval before activation.')

async def startup():
    validate_staging()
    # All public front-ends of this service are valid same-origin hosts for
    # candidate POSTs; no extra Render configuration step is required for the
    # custom domain. APP_EXTRA_ORIGINS (if set) adds more.
    from .hybrid_provider import hybrid_ai_or_evidence_only
    configured=set(filter(None,(v.strip().rstrip('/') for v in os.getenv('APP_EXTRA_ORIGINS','').split(','))))
    trusted=','.join(sorted({*PUBLIC_ORIGINS,os.getenv('APP_ORIGIN','').rstrip('/'),*configured}))
    os.environ['APP_EXTRA_ORIGINS']=trusted
    bridge.backend=await asyncio.to_thread(WorkspaceApp,ai=hybrid_ai_or_evidence_only())

app=Starlette(routes=[Route('/v2-pcm-worklet.js',bridge.pcm_worklet),
    WebSocketRoute('/api/v2/voice/{aid}',bridge.voice),Mount('/',app=bridge.http_app)],
    on_startup=[startup],on_shutdown=[bridge.shutdown])
