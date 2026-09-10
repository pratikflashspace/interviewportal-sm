"""ASGI voice bridge, opt-in staging only; one process required."""
import asyncio
import base64
import json
import logging
import os
import re
import time
from pathlib import Path
from urllib.parse import urlencode
from starlette.applications import Starlette
from starlette.middleware.wsgi import WSGIMiddleware
from starlette.responses import Response
from starlette.routing import Mount, Route, WebSocketRoute
from websockets.asyncio.client import connect as WebSocketConnect
from .v2_endpoint import create_app
from .v2_speech_events import SpeechEvents

LOG=logging.getLogger('flashspace.voice')
class connect(WebSocketConnect):
    def process_redirect(self, exc):return exc

UPSTREAM='wss://api.sarvam.ai/speech-to-text-realtime/ws'
EVENTS={'vad.speech_start','vad.speech_end','transcript.partial','transcript.final'}

def clean_event(value):
    if not isinstance(value,dict) or value.get('event') not in EVENTS:return None
    result={'event':value['event']};index=value.get('utterance_idx')
    if type(index) is not int or index<0:return None
    result['utterance_idx']=index
    if value['event'].startswith('transcript.'):
        text=value.get('text')
        if not isinstance(text,str) or len(text)>6000:return None
        result['text']=text
    return result

backend=None
# Identity-bearing leases: late cleanup must never remove a newer connection.
active={}

def release_lease(aid,lease):
    if active.get(aid) is lease:
        del active[aid]

async def startup():
    global backend
    backend=await asyncio.to_thread(create_app)

async def shutdown():
    if backend:backend.stop.set();backend.job_wakeup.set()

async def pcm_worklet(request):
    source=Path(__file__).resolve().parents[1]/'web/src/v2/pcm-worklet.js'
    return Response(source.read_text(),media_type='application/javascript',headers={'Cache-Control':'no-store','X-Content-Type-Options':'nosniff'})

async def voice(socket):
    aid=socket.path_params['aid']
    if backend is None or socket.headers.get('origin')!=backend.origin or not re.fullmatch(r'[\w-]{1,80}',aid):
        LOG.warning('voice_rejected reason=origin_or_configuration')
        await socket.close(code=1008);return
    env={'HTTP_COOKIE':socket.headers.get('cookie','')}
    async def authorized():
        def check():
            u=backend.current_user(env);a=backend.store.get(aid);f=backend.flow(aid)
            if a['user_id']!=u['id'] or not f or f['status']!='interview':raise ValueError()
            return a
        return await asyncio.to_thread(check)
    try:a=await authorized()
    except Exception:
        LOG.warning('voice_rejected reason=session_or_ownership')
        await socket.close(code=1008);return
    if aid in active:
        LOG.warning('voice_rejected reason=active_connection')
        await socket.close(code=1008);return
    lease=object();active[aid]=lease;phase='quota';disconnected=False
    try:
        await asyncio.to_thread(backend.ai_quota,a,'voice-session-v2',24)
        phase='configuration'
        key=os.getenv('SARVAM_API_KEY','').strip()
        if not key or any(c.isspace() for c in key):raise ValueError()
        await socket.accept();phase='provider_connect'
        query=urlencode({'language_code':'en-IN','model':'saaras:v3-realtime','encoding':'linear16',
                         'sample_rate':16000,'stream_type':'balanced','endpointing':'vad',
                         'silence_duration_ms':1500,'min_speech_duration_ms':250})
        async with connect(UPSTREAM+'?'+query,additional_headers={'api-subscription-key':key},
                           open_timeout=15,close_timeout=5,max_size=65536,max_queue=8,ping_interval=20) as upstream:
            phase='stream';await socket.send_json({'event':'ready'});started=time.monotonic();total=0
            async def send_audio():
                nonlocal total,disconnected
                while True:
                    msg=await socket.receive()
                    if msg['type']=='websocket.disconnect':disconnected=True;return
                    frame=msg.get('bytes')
                    if frame is None or len(frame)==0 or len(frame)>6400 or len(frame)%2:raise ValueError()
                    total+=len(frame);elapsed=time.monotonic()-started
                    if total>32000*(elapsed+2) or total>32000*1800:raise ValueError()
                    await upstream.send(json.dumps({'event':'audio_input','audio':base64.b64encode(frame).decode()}))
            async def receive_events():
                guard=SpeechEvents()
                async for message in upstream:
                    value=json.loads(message)
                    if value.get('event')=='error':raise ValueError()
                    cleaned=clean_event(value)
                    if cleaned:
                        forwarded=guard.accept(cleaned)
                        if forwarded:await socket.send_json(forwarded)
            async def auth_watch():
                while True:
                    await asyncio.sleep(15);await authorized()
                    if time.monotonic()-started>1800:raise ValueError()
                    await upstream.send(json.dumps({'event':'ping'}))
            tasks=[asyncio.create_task(f()) for f in (send_audio,receive_events,auth_watch)]
            try:
                done,_=await asyncio.wait(tasks,return_when=asyncio.FIRST_COMPLETED)
                for task in done:task.result()
            finally:
                for task in tasks:task.cancel()
                await asyncio.gather(*tasks,return_exceptions=True)
                # No forwarding/auth tasks remain. Free the application lease
                # BEFORE __aexit__ waits for the provider's close handshake.
                # Browser close/reconnect can now proceed without a spurious 403.
                release_lease(aid,lease)
                LOG.info('voice_stream_stopped forwarding_tasks=0')
                phase='provider_close'
    except Exception:
        # Only allowlisted phases are logged; no keys, URLs, candidate IDs,
        # transcripts or raw upstream exceptions.
        LOG.warning('voice_failed phase=%s',phase)
        if not disconnected:
            try:await socket.send_json({'event':'error','message':'Voice connection unavailable. Pause and reconnect or use typing.'})
            except Exception:pass
    finally:
        release_lease(aid,lease)
        try:await socket.close(code=1000)
        except Exception:pass

async def http_app(scope,receive,send):
    if backend is None:raise RuntimeError('Application has not started')
    await WSGIMiddleware(backend)(scope,receive,send)

app=Starlette(routes=[Route('/v2-pcm-worklet.js',pcm_worklet),WebSocketRoute('/api/v2/voice/{aid}',voice),Mount('/',app=http_app)],
              on_startup=[startup],on_shutdown=[shutdown])
