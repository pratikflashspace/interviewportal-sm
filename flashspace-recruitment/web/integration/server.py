"""Synthetic CI fixture ONLY. No external provider/database credentials.
Real ASGI/WSGI application, SQL, authentication, UI, websocket bridge and media.
Sarvam events/TTS and ClickUp HTTP responses are explicitly synthetic boundaries.
"""
import asyncio,io,json,math,os,struct,sys,tempfile,wave
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'tests'))
if os.getenv('CI')!='true' or os.getenv('DATABASE_URL') or os.getenv('RENDER') or os.getenv('CLICKUP_API_TOKEN'):
    raise RuntimeError('Synthetic fixture must run only in isolated CI without external credentials.')
from starlette.applications import Starlette
from starlette.routing import Route,WebSocketRoute,Mount
from backend import v2_stream as bridge
from backend.workspace_server import WorkspaceApp,RECRUITER_EMAIL
from backend.server import hash_password,now
from backend.v2_endpoint import EvidenceOnlyAI
from test_workspace_interview_journey import Provider,BoundaryClickUp
from test_backend import ROLE
os.environ['APP_ORIGIN']='http://127.0.0.1:8765';os.environ['SARVAM_API_KEY']='synthetic-ci-not-a-provider-key'
root=tempfile.TemporaryDirectory()
buffer=io.BytesIO()
with wave.open(buffer,'wb') as wav:
    wav.setnchannels(1);wav.setsampwidth(2);wav.setframerate(16000)
    wav.writeframes(b''.join(struct.pack('<h',int(4000*math.sin(2*math.pi*440*i/16000))) for i in range(16000)))
AUDIO=buffer.getvalue()
class SyntheticProvider(Provider):
    def speech(self,q):self.spoken.append(q);return AUDIO
class SyntheticSocket:
    def __init__(self):self.index=0
    async def send(self,message):pass
    def __aiter__(self):return self
    async def __anext__(self):
        events=[{'event':'vad.speech_start','utterance_idx':0},{'event':'transcript.final','utterance_idx':0,'text':'Synthetic candidate describes a relevant project and their personal contribution.'},{'event':'vad.speech_end','utterance_idx':0}]
        if self.index>=len(events):await asyncio.Future()
        await asyncio.sleep(6 if self.index==0 else .15)
        value=events[self.index];self.index+=1;return json.dumps(value)
class SyntheticConnect:
    async def __aenter__(self):return SyntheticSocket()
    async def __aexit__(self,*args):pass
async def startup():
    ai=EvidenceOnlyAI();ai.provider=SyntheticProvider()
    backend=WorkspaceApp(db_path=root.name+'/fixture.db',roles=[ROLE],ai=ai,start_worker=False,recording_root=root.name+'/recordings')
    backend.clickup=BoundaryClickUp(backend.store)
    with backend.store.db() as db:
        db.execute('INSERT INTO settings VALUES (?,?)',('v2-bank:growth','sales'))
        db.execute('INSERT INTO users VALUES (?,?,?,?,1,?)',('synthetic-recruiter',RECRUITER_EMAIL,'Synthetic Recruiter',hash_password('synthetic-browser-password-123'),now()))
    bridge.backend=backend;bridge.connect=lambda *args,**kwargs:SyntheticConnect()
    async def worker():
        while True:
            await asyncio.sleep(2);await asyncio.to_thread(backend.work_once)
    app.state.worker=asyncio.create_task(worker())
async def shutdown():
    app.state.worker.cancel();await asyncio.gather(app.state.worker,return_exceptions=True);root.cleanup()
app=Starlette(routes=[Route('/v2-pcm-worklet.js',bridge.pcm_worklet),WebSocketRoute('/api/v2/voice/{aid}',bridge.voice),Mount('/',app=bridge.http_app)],on_startup=[startup],on_shutdown=[shutdown])
if __name__=='__main__':
    import uvicorn
    uvicorn.run(app,host='127.0.0.1',port=8765,log_level='warning',access_log=False)
