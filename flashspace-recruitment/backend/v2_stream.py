"""ASGI voice bridge. Run only on isolated staging after streaming-access validation.

uvicorn backend.v2_stream:app --host 0.0.0.0 --port $PORT --workers 1
Cookies authenticate the browser; the provider key never leaves the server.
"""
import asyncio
import base64
import json
import os
import re
import time
from urllib.parse import urlencode
from starlette.applications import Starlette
from starlette.middleware.wsgi import WSGIMiddleware
from starlette.routing import Mount, WebSocketRoute
from websockets.asyncio.client import connect
from .v2_server import create_app

UPSTREAM='wss://api.sarvam.ai/speech-to-text-realtime/ws'
EVENTS={'vad.speech_start','vad.speech_end','transcript.partial','transcript.final'}


def clean_event(value):
    if not isinstance(value,dict) or value.get('event') not in EVENTS:return None
    result={'event':value['event']}
    index=value.get('utterance_idx')
    if type(index) is not int or index<0:return None
    result['utterance_idx']=index
    if value['event'].startswith('transcript.'):
        text=value.get('text')
        if not isinstance(text,str) or len(text)>6000:return None
        result['text']=text
    return result


# Construct on lifespan startup, not import: tests/imports never initialize a DB.
backend=None
active=set()


async def startup():
    global backend
    backend=await asyncio.to_thread(create_app)


async def shutdown():
    if backend:backend.stop.set();backend.job_wakeup.set()


async def voice(socket):
    aid=socket.path_params['aid']
    if backend is None or socket.headers.get('origin')!=backend.origin or not re.fullmatch(r'[\w-]{1,80}',aid):
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
        await socket.close(code=1008);return
    if aid in active:
        await socket.close(code=1008);return
    active.add(aid)
    try:
        # Per-application limits plus global application quota. Not a billing cap.
        await asyncio.to_thread(backend.ai_quota,a,'voice-session-v2',24)
        key=os.getenv('SARVAM_API_KEY','').strip()
        if not key or any(c.isspace() for c in key):raise ValueError()
        await socket.accept()
        query=urlencode({'language_code':'en-IN','model':'saaras:v3-realtime','encoding':'linear16',
                         'sample_rate':16000,'stream_type':'balanced','endpointing':'vad',
                         'silence_duration_ms':1500,'min_speech_duration_ms':250})
        async with connect(UPSTREAM+'?'+query, additional_headers={'api-subscription-key':key},
                           open_timeout=15,close_timeout=5,max_size=65536,max_queue=8,ping_interval=20) as upstream:
            await socket.send_json({'event':'ready'})
            started=time.monotonic();total=0
            async def send_audio():
                nonlocal total
                while True:
                    msg=await socket.receive()
                    if msg['type']=='websocket.disconnect':return
                    frame=msg.get('bytes')
                    if frame is None or len(frame)==0 or len(frame)>6400 or len(frame)%2:
                        raise ValueError('Invalid PCM frame')
                    total+=len(frame)
                    elapsed=time.monotonic()-started
                    # Allow 2 seconds burst slack, then cap to real-time PCM rate.
                    if total>32000*(elapsed+2) or total>32000*1800:raise ValueError('Audio budget exceeded')
                    await upstream.send(json.dumps({'event':'audio_input','audio':base64.b64encode(frame).decode()}))
            async def receive_events():
                async for message in upstream:
                    value=json.loads(message)
                    if value.get('event')=='error':raise ValueError('Provider stream error')
                    cleaned=clean_event(value)
                    if cleaned:await socket.send_json(cleaned)
            async def auth_watch():
                while True:
                    await asyncio.sleep(15)
                    await authorized()
                    if time.monotonic()-started>1800:raise ValueError('Session budget exceeded')
            tasks=[asyncio.create_task(f()) for f in (send_audio,receive_events,auth_watch)]
            try:
                done,_=await asyncio.wait(tasks,return_when=asyncio.FIRST_COMPLETED)
                for task in done:task.result()
            finally:
                for task in tasks:task.cancel()
                await asyncio.gather(*tasks,return_exceptions=True)
    except Exception:
        # Never echo upstream exception/key/transcript. Close and let UI pause.
        try:await socket.send_json({'event':'error','message':'Voice connection unavailable. Pause and reconnect or use typing.'})
        except Exception:pass
    finally:
        active.discard(aid)
        try:await socket.close(code=1000)
        except Exception:pass


async def http_app(scope, receive, send):
    if backend is None:raise RuntimeError('Application has not started')
    await WSGIMiddleware(backend)(scope,receive,send)

app=Starlette(routes=[WebSocketRoute('/api/v2/voice/{aid}',voice),Mount('/',app=http_app)],
              on_startup=[startup],on_shutdown=[shutdown])
