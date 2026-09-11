"""Temporary interview-bound recordings; no floating or standalone capture API.

Limits include incomplete recordings. Instance-local bytes are explicitly not a
permanent archive. One process required. No migration of existing applications.
"""
import hashlib
import json
import os
import re
import threading
import uuid
from pathlib import Path
from .server import APIError,now
from .v2_server import V2ClickUp
from .v2_endpoint import ConversationalApp,EvidenceOnlyAI

MAX_FILES=10
MAX_BYTES=50*1024*1024
MAX_CHUNK=1024*1024

class RecordingStore:
    def __init__(self,root):
        self.root=Path(root);self.root.mkdir(parents=True,exist_ok=True,mode=0o700);self.lock=threading.RLock()
    def path(self,rid):
        if not isinstance(rid,str) or not re.fullmatch(r'[a-f0-9]{32}',rid):raise APIError(404,'Recording unavailable.')
        return self.root/rid
    def get(self,rid):
        try:return json.loads((self.path(rid)/'manifest.json').read_text())
        except FileNotFoundError:raise APIError(404,'Temporary recording unavailable; the server may have been replaced.') from None
    def save(self,m):
        path=self.path(m['id']);tmp=path/'manifest.tmp';tmp.write_text(json.dumps(m));os.replace(tmp,path/'manifest.json')
    def all(self,aid):
        result=[]
        for path in self.root.glob('*/manifest.json'):
            try:
                m=json.loads(path.read_text())
                if m['application_id']==aid:result.append(m)
            except (ValueError,OSError,KeyError):continue
        return sorted(result,key=lambda m:m['created_at'])
    def create(self,aid,uid,mime):
        if mime not in ('video/webm','video/mp4'):raise APIError(400,'Unsupported recording format.')
        with self.lock:
            if any(m['status']=='uploading' for m in self.all(aid)):
                raise APIError(409,'This interview has an unfinished recording. Ask the recruiter to review it before starting another recording.')
            if sum(p.is_dir() for p in self.root.iterdir())>=MAX_FILES:raise APIError(409,'Temporary recording capacity reached. Do not start capture; ask the recruiter to download and remove a copy.')
            rid=uuid.uuid4().hex;self.path(rid).mkdir(mode=0o700)
            m={'id':rid,'application_id':aid,'owner':uid,'mime':mime,'status':'uploading','bytes':0,'chunks':[],
               'created_at':now(),'consent':'integrated-interview-av-v1','temporary':True}
            self.save(m);return m
    def append(self,rid,index,data):
        with self.lock:
            m=self.get(rid);sha=hashlib.sha256(data).hexdigest()
            if type(index) is not int or index<0 or not 1<=len(data)<=MAX_CHUNK:raise APIError(400,'Invalid recording chunk.')
            if index<len(m['chunks']):
                if m['chunks'][index]['sha']!=sha:raise APIError(409,'Recording chunk conflict.')
                return m
            if m['status']!='uploading' or index!=len(m['chunks']):raise APIError(409,'Recording chunk is out of order.')
            if m['bytes']+len(data)>MAX_BYTES:raise APIError(413,'Recording exceeds 50 MB.')
            valid=data.startswith(b'\x1aE\xdf\xa3') if m['mime']=='video/webm' else len(data)>8 and data[4:8]==b'ftyp'
            if index==0 and not valid:raise APIError(400,'Invalid recording container.')
            (self.path(rid)/f'{index}.part').write_bytes(data)
            m['chunks'].append({'sha':sha,'size':len(data)});m['bytes']+=len(data);self.save(m);return m
    def finish(self,rid,count):
        with self.lock:
            m=self.get(rid)
            if type(count) is not int or count<=0 or count!=len(m['chunks']):raise APIError(409,'Recording is incomplete.')
            if any(not (self.path(rid)/f'{i}.part').exists() for i in range(count)):raise APIError(409,'Recording data missing.')
            m['status']='ready';self.save(m);return m
    def remove(self,rid):
        with self.lock:
            m=self.get(rid)
            if m['status']=='uploading':raise APIError(409,'Unfinished capture cannot be removed through this route.')
            for file in self.path(rid).iterdir():file.unlink()
            self.path(rid).rmdir()

class InterviewRecordingClickUp(V2ClickUp):
    @staticmethod
    def description(a):
        text=V2ClickUp.description(a)
        if a.get('recording_review_url'):
            text+='\n\nINTERVIEW RECORDING\n'+a['recording_review_url']+'\nRecruiter login required. Temporary recording: download promptly. May be lost on server replacement.'
        return text

class IntegratedApp(ConversationalApp):
    def __init__(self,*args,recording_root=None,**kwargs):
        start=kwargs.pop('start_worker',True)
        super().__init__(*args,start_worker=False,**kwargs)
        self.recordings=RecordingStore(recording_root or os.getenv('TEMP_RECORDINGS_DIR','/tmp/flashspace-integrated-recordings'))
        if kwargs.get('clickup') is None:self.clickup=InterviewRecordingClickUp(self.store)
        if start:threading.Thread(target=self.worker,daemon=True).start()
    @staticmethod
    def metadata(m):return {k:v for k,v in m.items() if k not in ('owner','chunks')}
    def route(self,env,body):
        path=env.get('PATH_INFO','');method=env.get('REQUEST_METHOD')
        match=re.fullmatch(r'/api/v2/applications/([\w-]+)/recording',path)
        if match:
            user=self.current_user(env);aid=match[1]
            with self.lock:
                a=self.store.get(aid);f=self.flow(aid)
                if a['user_id']!=user['id'] or not f:raise APIError(404,'Interview not found.')
                if method!='POST':raise APIError(405,'POST required.')
                if f['status']!='interview' or not f['active']:raise APIError(409,'This interview is not ready to start recording.')
                if body.get('consent')!='integrated-interview-av-v1':raise APIError(400,'Explicit audio/video recording consent is required.')
                self.store.quota('capture:'+user['id'],20,3600)
                m=self.recordings.create(aid,user['id'],body.get('mime'))
                return {**self.metadata(m),'max_bytes':MAX_BYTES,'max_seconds':1800},[]
        match=re.fullmatch(r'/api/admin/applications/([\w-]+)/recordings',path)
        if match and method=='GET':
            user=self.current_user(env)
            if not user['admin']:raise APIError(403,'Recruiter access required.')
            a=self.store.get(match[1])
            return {'application_id':a['id'],'candidate':a['name'],'role':a['role_title'],
                    'recordings':[self.metadata(m) for m in self.recordings.all(a['id'])]},[]
        match=re.fullmatch(r'/api/recordings/([a-f0-9]{32})/(finish|remove)',path)
        if match and method=='POST':
            user=self.current_user(env);rid,action=match.groups();m=self.recordings.get(rid)
            if action=='remove':
                if not user['admin']:raise APIError(403,'Recruiter access required.')
                self.recordings.remove(rid);return {'removed':True},[]
            if m['owner']!=user['id']:raise APIError(404,'Recording not found.')
            m=self.recordings.finish(rid,body.get('chunks'))
            with self.lock:
                a=self.store.get(m['application_id'])
                a['recording_review_url']=self.origin+'/interview-review?application='+a['id']
                self.store.save(a)
            self.job_wakeup.set();return self.metadata(m),[]
        # Metadata for route-aware application UI. Do not expose future questions.
        result,headers=super().route(env,body)
        if path in ('/api/applications','/api/admin/applications') and method=='GET':
            for a in result:
                f=self.flow(a['id'])
                a['flow_version']=2 if f else 1
                if f:a['interview_url']='/interview-v2?application='+a['id']
        return result,headers

    def __call__(self,env,start_response):
        def headers(status,items):
            items=[(k,v) for k,v in items if k.lower()!='permissions-policy']
            start_response(status,items+[('Permissions-Policy','camera=(self), microphone=(self)')])
        match=re.fullmatch(r'/api/recordings/([a-f0-9]{32})/(chunk/(\d+)|media)',env.get('PATH_INFO',''))
        if not match:return super().__call__(env,headers)
        try:
            user=self.current_user(env);rid,action,index=match.groups();m=self.recordings.get(rid)
            if action.startswith('chunk/'):
                if m['owner']!=user['id']:raise APIError(404,'Recording not found.')
                if env.get('REQUEST_METHOD')!='POST':raise APIError(405,'POST required.')
                if env.get('HTTP_ORIGIN')!=self.origin or env.get('HTTP_X_REQUESTED_WITH')!='Flashspace':raise APIError(403,'Origin rejected.')
                length=int(env.get('CONTENT_LENGTH') or 0)
                if not 1<=length<=MAX_CHUNK:raise APIError(413,'Chunk exceeds 1 MB.')
                data=env['wsgi.input'].read(length)
                if len(data)!=length:raise APIError(400,'Incomplete request.')
                m=self.recordings.append(rid,int(index),data)
                headers('200 OK',[('Content-Type','application/json'),('Cache-Control','no-store')]);return [json.dumps({'chunks':len(m['chunks'])}).encode()]
            if not user['admin']:raise APIError(403,'Recruiter access required.')
            if env.get('REQUEST_METHOD') not in ('GET','HEAD'):raise APIError(405,'GET required.')
            if m['status']!='ready':raise APIError(409,'Recording is incomplete.')
            total=m['bytes'];start,end=0,total-1;status='200 OK'
            if env.get('HTTP_RANGE'):
                r=re.fullmatch(r'bytes=(\d*)-(\d*)',env['HTTP_RANGE'])
                if not r or not any(r.groups()):raise APIError(416,'Invalid byte range.')
                if r[1]:start=int(r[1]);end=min(int(r[2]) if r[2] else total-1,total-1)
                else:start=max(0,total-int(r[2]))
                if start>end or start>=total:raise APIError(416,'Invalid byte range.')
                status='206 Partial Content'
            h=[('Content-Type',m['mime']),('Content-Length',str(end-start+1)),('Accept-Ranges','bytes'),('Cache-Control','no-store'),('X-Content-Type-Options','nosniff')]
            if status.startswith('206'):h.append(('Content-Range',f'bytes {start}-{end}/{total}'))
            headers(status,h)
            if env.get('REQUEST_METHOD')=='HEAD':return [b'']
            def stream():
                offset=0
                for i,part in enumerate(m['chunks']):
                    left=max(0,start-offset);right=min(part['size'],end-offset+1)
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
        except APIError as exc:error=exc
        except (ValueError,TypeError):error=APIError(400,'Invalid recording request.')
        except Exception:error=APIError(500,'Recording operation failed. Keep your local download.')
        from http import HTTPStatus
        headers(f'{error.status} {HTTPStatus(error.status).phrase}',[('Content-Type','application/json'),('Cache-Control','no-store')])
        return [json.dumps({'error':error.message}).encode()]


def create_app():return IntegratedApp(ai=EvidenceOnlyAI())
