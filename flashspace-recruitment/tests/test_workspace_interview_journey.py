"""Integrated application journey; mock ONLY Sarvam and ClickUp boundaries.
Uses real WorkspaceApp, SQL, permissions, replay/draft/recording/flow/report logic.
Synthetic WebM bytes exercise transport, not browser playback or real provider AI.
"""
import io,json,os,tempfile,time,unittest
from unittest.mock import patch
from backend.workspace_server import WorkspaceApp,RECRUITER_EMAIL
from backend.v2_endpoint import EvidenceOnlyAI
from backend.v2_server import CRITERIA
from backend.integrated_recordings import InterviewRecordingClickUp
from backend.server import APIError,hash_password,now
from test_backend import ROLE

class Provider:
    model='synthetic-boundary'
    def __init__(self):self.fail_speech=False;self.spoken=[]
    def speech(self,question):
        if self.fail_speech:raise APIError(502,'Synthetic speech failure')
        self.spoken.append(question);return b'synthetic-audio-not-playable'
    def structured(self,system,payload,name,schema):
        if name=='followup_choice':return {'choice':-1,'gap':''}
        if name=='turn_completion':return {'decision':'complete'}
        if name=='v2_evidence_report':
            result=[]
            for c in CRITERIA:
                stage='domain' if c in CRITERIA[-2:] else 'generic'
                a=next(a for a in payload['answers'] if a['stage']==stage)
                result.append({'name':c,'reason':'Synthetic evidence for integration testing only.','evidence':a['answer'],'source_id':a['question_id'],'confidence':'low'})
            return {'summary':'Synthetic interview evidence; human review required.','criteria':result}
        raise AssertionError(name)

class BoundaryClickUp(InterviewRecordingClickUp):
    def __init__(self,store):super().__init__(store);self.payloads=[];self.fail=False
    def list_id(self,role):return 'synthetic-list'
    def call(self,method,path,data=None):
        if self.fail:raise APIError(502,'Synthetic ClickUp failure')
        if method=='GET':return {'tasks':[],'last_page':True}
        self.payloads.append(data)
        return {'id':'synthetic-task','url':'https://example.com/synthetic-task'}

class JourneyTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        p=patch.dict(os.environ,{'APP_ORIGIN':'http://localhost:8000'});p.start();self.addCleanup(p.stop)
        self.clock=time.time();p=patch('time.time',side_effect=lambda:self.clock);p.start();self.addCleanup(p.stop)
        self.provider=Provider();self.ai=EvidenceOnlyAI();self.ai.provider=self.provider
        self.app=WorkspaceApp(db_path=self.tmp.name+'/test.db',roles=[ROLE],ai=self.ai,start_worker=False,recording_root=self.tmp.name+'/recordings');self.cookie=''
        self.clickup=BoundaryClickUp(self.app.store);self.app.clickup=self.clickup
        with self.app.store.db() as db:db.execute('INSERT INTO settings VALUES (?,?)',('v2-bank:growth','sales'))
    def req(self,path,body=None,cookie=None,origin=None,byte_range=None):
        raw=isinstance(body,bytes);data=body if raw else json.dumps(body or {}).encode()
        env={'REQUEST_METHOD':'POST' if body is not None else 'GET','PATH_INFO':path,'REMOTE_ADDR':'synthetic','CONTENT_TYPE':'application/octet-stream' if raw else 'application/json','CONTENT_LENGTH':str(len(data)),'wsgi.input':io.BytesIO(data),'HTTP_ORIGIN':origin or self.app.origin,'HTTP_X_REQUESTED_WITH':'Flashspace','HTTP_COOKIE':self.cookie if cookie is None else cookie}
        if byte_range:env['HTTP_RANGE']=byte_range
        r={}
        def start(s,h):r.update(status=int(s.split()[0]),headers=dict(h))
        out=b''.join(self.app(env,start));r['body']=json.loads(out) if 'application/json' in r['headers'].get('Content-Type','') else out
        if 'Set-Cookie' in r['headers']:self.cookie=r['headers']['Set-Cookie'].split(';')[0]
        return r
    def ok(self,path,body=None,**kw):
        r=self.req(path,body,**kw);self.assertEqual(r['status'],200,r);return r['body']
    def signup(self,email='candidate@example.com'):
        self.ok('/api/auth/candidate/signup',{'name':'Synthetic Candidate','email':email,'password':'synthetic-password-123','confirm_password':'synthetic-password-123'})
    def new_application(self):
        self.signup();return self.ok('/api/v2/applications',{'role_id':'growth','experience':'Synthetic experience for integration testing only.','portfolio':'https://example.com/resume','consent':True,'consent_version':'flashspace-sarvam-conversation-v2'})
    def recruiter(self):
        with self.app.store.db() as db:db.execute('INSERT INTO users VALUES (?,?,?,?,1,?)',('synthetic-recruiter',RECRUITER_EMAIL,'Synthetic Recruiter',hash_password('synthetic-password-123'),now()))
        self.ok('/api/auth/recruiter/login',{'email':RECRUITER_EMAIL,'password':'synthetic-password-123'})
    def test_complete_candidate_to_recruiter_journey(self):
        f=self.new_application();aid=f['application_id'];base='/api/v2/applications/'+aid;candidate_cookie=self.cookie
        self.assertEqual(self.app.recordings.all(aid),[])
        self.ok(base+'/intro',{})
        intro=self.provider.spoken[-1].lower()
        for forbidden in ('six','four','pause','typing'):self.assertNotIn(forbidden,intro)
        self.assertEqual(self.req(base+'/recording',{'mime':'video/webm'})['status'],400)
        rid=self.ok(base+'/recording',{'mime':'video/webm','consent':'integrated-interview-av-v1'})['id'];media='/api/recordings/'+rid
        video=b'\x1aE\xdf\xa3'+b'synthetic-video-transport'*20
        self.ok(media+'/chunk/0',video);self.ok(media+'/chunk/0',video)
        self.assertEqual(self.req(media+'/chunk/1',video,origin='https://wrong.example')['status'],403)
        first=f['active']['id']
        for i in range(3):self.ok(base+'/speech',{'question_id':first})
        self.assertEqual(self.req(base+'/speech',{'question_id':first})['status'],409)
        self.assertEqual(self.ok(base+'/playback')['replays_remaining'],0)
        for i in range(10):
            self.clock+=61
            qid=f['active']['id'];answer='Synthetic response '+str(i)+' describing a concrete contribution.'
            draft=self.ok(base+'/draft')
            self.ok(base+'/draft',{'question_id':qid,'revision':draft['revision'],'transcript':answer})
            self.assertEqual(self.ok(base+'/draft')['transcript'],answer)
            if i:self.ok(base+'/speech',{'question_id':qid})
            self.assertTrue(self.ok(base+'/end-check',{'question_id':qid,'version':f['version'],'answer':answer})['complete'])
            body={'event_id':'synthetic-event-'+str(i),'version':f['version'],'question_id':qid,'answer':answer}
            f=self.ok(base+'/answer',body)
            again=self.ok(base+'/answer',body);self.assertEqual(len(again['answers']),i+1)
            self.assertEqual(self.ok(base)['status'],f['status'])
        self.assertEqual(f['status'],'completed');self.assertEqual(len(f['answers']),10)
        self.assertEqual(sum(a['stage']=='generic' for a in f['answers']),6)
        self.assertEqual(sum(a['stage']=='domain' for a in f['answers']),4)
        self.ok(media+'/finish',{'chunks':1})
        self.assertEqual(self.req(media+'/media')['status'],403)
        self.clickup.fail=True;self.clock+=61;self.app.work_once()
        self.assertEqual(self.app.store.get(aid)['sync_status'],'Retry pending')
        self.assertEqual(len(self.app.store.get(aid)['answers']),10)
        self.clickup.fail=False;self.clock+=1000;self.app.work_once()
        self.assertEqual(self.app.store.get(aid)['sync_status'],'Synced')
        description=self.clickup.payloads[-1]['description']
        self.assertIn('Synthetic response 9',description)
        self.assertIn('/interview-review?application='+aid,description)
        self.assertIn('No aggregate score assigned',description)
        own=self.ok('/api/applications')[0];self.assertNotIn('evaluation',own)
        self.signup('other@example.com')
        self.assertEqual(self.req(base)['status'],404)
        self.assertEqual(self.req(media+'/chunk/1',video)['status'],404)
        self.recruiter()
        report=self.ok('/api/admin/v2/reports/'+aid)['report']
        self.assertEqual(report['scoring_status'],'not_scored');self.assertIsNone(report['score'])
        self.assertTrue(all('score' not in c for c in report['criteria']))
        self.assertEqual(len(self.ok('/api/admin/applications/'+aid+'/recordings')['recordings']),1)
        self.assertEqual(self.ok(media+'/media'),video)
        partial=self.req(media+'/media',byte_range='bytes=4-12');self.assertEqual(partial['status'],206);self.assertEqual(partial['body'],video[4:13])
        self.ok('/api/workspace/recruiter/applications/'+aid+'/stage',{'version':0,'stage':'shortlisted'})
        self.assertEqual(self.ok('/api/workspace/candidate/applications',cookie=candidate_cookie)[0]['stage'],'shortlisted')
    def test_failed_tts_refunds_replay_and_keeps_draft(self):
        f=self.new_application();base='/api/v2/applications/'+f['application_id'];qid=f['active']['id']
        d=self.ok(base+'/draft');self.ok(base+'/draft',{'question_id':qid,'revision':d['revision'],'transcript':'Synthetic saved draft'})
        self.provider.fail_speech=True
        self.assertEqual(self.req(base+'/speech',{'question_id':qid})['status'],502)
        self.assertEqual(self.ok(base+'/playback')['deliveries_remaining'],3)
        self.assertEqual(self.ok(base+'/draft')['transcript'],'Synthetic saved draft')
        self.provider.fail_speech=False;self.ok(base+'/speech',{'question_id':qid})
        self.assertEqual(self.ok(base+'/playback')['deliveries_remaining'],2)

if __name__=='__main__':unittest.main()
