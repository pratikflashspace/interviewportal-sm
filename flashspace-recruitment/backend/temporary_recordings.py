"""Ten TEMPORARY recordings per instance. No durable-storage guarantee.

One Gunicorn worker required. Files/manifests are outside web/dist, available
only through authenticated owner/recruiter endpoints. Never auto-evict videos.
"""
import hashlib
import json
import os
import re
import threading
import uuid
from pathlib import Path
from .role_server import RoleManagementApp
from .server import APIError,ClickUp,now

MAX_RECORDINGS=10
MAX_FILE=50*1024*1024
MAX_CHUNK=1024*1024

class TemporaryStore:
    def __init__(self,root):
        self.root=Path(root);self.root.mkdir(parents=True,exist_ok=True,mode=0o700)
        self.lock=threading.RLock()
    def path(self,rid):
        if not re.fullmatch(r'[a-f0-9]{32}',rid):raise APIError(404,'Recording not found.')
        return self.root/rid
    def get(self,rid):
        try:return json.loads((self.path(rid)/'manifest.json').read_text())
        except FileNotFoundError:raise APIError(404,'Recording unavailable. Temporary files may have been lost during a server replacement.') from None
    def save(self,m):
        p=self.path(m['id']);temp=p/'manifest.tmp'
        temp.write_text(json.dumps(m));os.replace(temp,p/'manifest.json')
    def all(self):
        result=[]
        for p in self.root.glob('*/manifest.json'):
            try:result.append(json.loads(p.read_text()))
            except (ValueError,OSError):pass
        return result
    def create(self,aid,uid,mime):
        if mime not in ('video/webm','video/mp4'):raise APIError(400,'Unsupported video format.')
        with self.lock:
            # Count even incomplete manifests/directories; no unbounded reservations.
            if sum(1 for p in self.root.iterdir() if p.is_dir())>=MAX_RECORDINGS:
                raise APIError(409,'All 10 temporary recording slots are used. Ask the recruiter to download and remove a recording.')
            rid=uuid.uuid4().hex;self.path(rid).mkdir(mode=0o700)
            m={'id':rid,'application_id':aid,'user_id':uid,'mime':mime,'bytes':0,'chunks':[],
               'status':'uploading','created_at':now(),'temporary':True}
            self.save(m);return m
    def append(self,rid,index,data):
        with self.lock:
            m=self.get(rid)
            if type(index) is not int or index<0 or not 1<=len(data)<=MAX_CHUNK:raise APIError(400,'Invalid recording chunk.')
            sha=hashlib.sha256(data).hexdigest()
            if index<len(m['chunks']):
                if m['chunks'][index]['sha']!=sha:raise APIError(409,'Chunk content conflicts with the uploaded recording.')
                return m
            if m['status']!='uploading' or index!=len(m['chunks']):raise APIError(409,'Chunk out of order.')
            if m['bytes']+len(data)>MAX_FILE:raise APIError(413,'Recording exceeds 50 MB. Keep the local download.')
            if index==0 and not (data.startswith(b'\x1aE\xdf\xa3') if m['mime']=='video/webm' else len(data)>=8 and data[4:8]==b'ftyp'):
                raise APIError(400,'Invalid recording container.')
            p=self.path(rid)/f'{index}.part';p.write_bytes(data)
            m['chunks'].append({'size':len(data),'sha':sha});m['bytes']+=len(data);self.save(m);return m
    def finish(self,rid,count):
        with self.lock:
            m=self.get(rid)
            if type(count) is not int or count!=len(m['chunks']) or not count:raise APIError(409,'Upload is incomplete.')
            # Serve parts as one byte stream, avoiding a second complete file on disk.
            if any(not (self.path(rid)/f'{i}.part').exists() for i in range(count)):raise APIError(409,'Upload parts are missing.')
            m['status']='ready';self.save(m);return m
    def remove(self,rid):
        with self.lock:
            p=self.path(rid);self.get(rid)
            for file in p.iterdir():file.unlink()
            p.rmdir()

class RecordingClickUp(ClickUp):
    @staticmethod
    def description(a):
        result=ClickUp.description(a)
        if a.get('recording_review_url'):
            result+='\n\nTEMPORARY INTERVIEW RECORDING\n'+a['recording_review_url']+'\nRecruiter login required. Download promptly; temporary server storage can disappear.'
        return result

class RecordingApp(RoleManagementApp):
    def __init__(self,*args,recording_root=None,**kwargs):
        start=kwargs.pop('start_worker',True)
        super().__init__(*args,start_worker=False,**kwargs)
        self.recordings=TemporaryStore(recording_root or os.getenv('TEMP_RECORDINGS_DIR','/tmp/flashspace-recordings'))
        if kwargs.get('clickup') is None:self.clickup=RecordingClickUp(self.store)
        if start:threading.Thread(target=self.worker,daemon=True).start()
    def owned(self,env,rid,admin=False):
        u=self.current_user(env);m=self.recordings.get(rid)
        if admin and not u['admin']:raise APIError(403,'Recruiter access required.')
        if not u['admin'] and u['id']!=m['user_id']:raise APIError(404,'Recording not found.')
        return u,m
    def route(self,env,body):
        path=env.get('PATH_INFO','');method=env.get('REQUEST_METHOD')
        if path=='/api/recordings' and method=='GET':
            u=self.current_user(env)
            return {'recordings':[m for m in self.recordings.all() if u['admin'] or m['user_id']==u['id']],
                    'capacity':10,'used':len(self.recordings.all()),'max_bytes':MAX_FILE,'temporary':True},[]
        if path=='/api/recordings' and method=='POST':
            u=self.current_user(env)
            if body.get('consent')!='temporary-av-v1':raise APIError(400,'Recording consent is required.')
            aid=body.get('application_id')
            if not isinstance(aid,str):raise APIError(400,'Choose a test application.')
            a=self.store.get(aid)
            if a['user_id']!=u['id']:raise APIError(404,'Application not found.')
            self.store.quota('recording-start:'+u['id'],20,3600)
            return self.recordings.create(aid,u['id'],body.get('mime')),[]
        match=re.fullmatch(r'/api/recordings/([a-f0-9]{32})/(finish|remove)',path)
        if match and method=='POST':
            rid,action=match.groups();u,m=self.owned(env,rid,action=='remove')
            if action=='remove':self.recordings.remove(rid);return {'removed':True},[]
            m=self.recordings.finish(rid,body.get('chunks'))
            with self.lock:
                a=self.store.get(m['application_id']);a['recording_review_url']=self.origin+'/recordings?recording='+rid
                self.store.save(a)
            self.job_wakeup.set();return m,[]
        return super().route(env,body)
    def __call__(self,env,start_response):
        path=env.get('PATH_INFO','');match=re.fullmatch(r'/api/recordings/([a-f0-9]{32})/(chunk/(\d+)|media)',path)
        def headers(status,h):
            # Same-origin camera permission only; no third-party frame access.
            h=[(k,v) for k,v in h if k.lower()!='permissions-policy']
            start_response(status,h+[('Permissions-Policy','camera=(self), microphone=(self)')])
        if not match:return super().__call__(env,headers)
        try:
            rid,action,index=match.groups();u,m=self.owned(env,rid)
            if action.startswith('chunk/'):
                if env.get('REQUEST_METHOD')!='POST':raise APIError(405,'POST required.')
                if env.get('HTTP_ORIGIN')!=self.origin or env.get('HTTP_X_REQUESTED_WITH')!='Flashspace':raise APIError(403,'Request origin rejected.')
                size=int(env.get('CONTENT_LENGTH') or 0)
                if not 1<=size<=MAX_CHUNK:raise APIError(413,'Chunk exceeds 1 MB.')
                data=env['wsgi.input'].read(size)
                if len(data)!=size:raise APIError(400,'Incomplete upload request.')
                result=self.recordings.append(rid,int(index),data)
                payload=json.dumps({'bytes':result['bytes'],'chunks':len(result['chunks'])}).encode()
                headers('200 OK',[('Content-Type','application/json'),('Cache-Control','no-store')]);return [payload]
            if env.get('REQUEST_METHOD') not in ('GET','HEAD'):raise APIError(405,'GET required.')
            if not u['admin']:raise APIError(403,'Recruiter access required for server playback.')
            if m['status']!='ready':raise APIError(409,'Recording upload not complete.')
            total=m['bytes'];start,end=0,total-1;status='200 OK'
            value=env.get('HTTP_RANGE')
            if value:
                r=re.fullmatch(r'bytes=(\d*)-(\d*)',value)
                if not r or not any(r.groups()):raise APIError(416,'Invalid range.')
                if r[1]:start=int(r[1]);end=min(int(r[2]) if r[2] else total-1,total-1)
                else:start=max(0,total-int(r[2]))
                if start>end or start>=total:raise APIError(416,'Range outside recording.')
                status='206 Partial Content'
            h=[('Content-Type',m['mime']),('Content-Length',str(end-start+1)),('Accept-Ranges','bytes'),('Cache-Control','no-store'),('X-Content-Type-Options','nosniff'),('Content-Disposition','inline; filename="interview.'+('webm' if m['mime']=='video/webm' else 'mp4')+'"')]
            if status.startswith('206'):h.append(('Content-Range',f'bytes {start}-{end}/{total}'))
            headers(status,h)
            if env.get('REQUEST_METHOD')=='HEAD':return [b'']
            def stream():
                offset=0
                for i,part in enumerate(m['chunks']):
                    left=max(start-offset,0);right=min(end-offset+1,part['size'])
                    if left<right:
                        try:
                            with (self.recordings.path(rid)/f'{i}.part').open('rb') as f:
                                f.seek(left);remaining=right-left
                                while remaining:
                                    data=f.read(min(65536,remaining))
                                    if not data:return
                                    remaining-=len(data);yield data
                        except FileNotFoundError:return
                    offset+=part['size']
            return stream()
        except (ValueError,TypeError):e=APIError(400,'Invalid upload request.')
        except APIError as exc:e=exc
        except Exception:e=APIError(500,'Recording operation failed; retain your local download.')
        from http import HTTPStatus
        headers(f'{e.status} {HTTPStatus(e.status).phrase}',[('Content-Type','application/json'),('Cache-Control','no-store')])
        return [json.dumps({'error':e.message}).encode()]

def create_app():
    from .sarvam_server import SarvamAI
    return RecordingApp(ai=SarvamAI())
