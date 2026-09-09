import io,json,os,tempfile,unittest
from unittest.mock import patch
from backend.server import App,APIError,AI,ClickUp,hash_password,verify_password
ROLE={'id':'growth','title':'Growth & Partnerships','department':'Growth','location':'New Delhi','type':'Full-time','experience':'1-3 years','description':'Build partnerships.','details':'Develop measurable partner programs.','skills':['Partnerships'],'published':True}
class FakeAI:
    def __init__(self): self.questions=0;self.evaluations=0;self.fail=False
    def next_question(self,role,answers):
        if self.fail: raise APIError(502,'Provider failed.')
        self.questions+=1;return f'Question {len(answers)+1}: How did you measure and improve your work?'
    def evaluate(self,role,answers):
        if self.fail: raise APIError(502,'Provider failed.')
        self.evaluations+=1
        return {'summary':'Claims require human verification.','score':60,'model':'fake','rubric_version':'test','criteria':[]}
    def transcribe(self,body,mime):return {'text':'A mocked transcript for transport testing.'}
    def speech(self,q):return b'fake-audio'
class FakeClickUp:
    def __init__(self):self.records=[];self.fail=False
    def sync(self,a):
        if self.fail: raise APIError(502,'ClickUp failed.')
        self.records.append(dict(a));return 'task-test','https://example.com/task-test'
class BackendTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.ai=FakeAI();self.cu=FakeClickUp()
        self.env=patch.dict(os.environ,{'ADMIN_EMAIL':'','APP_ORIGIN':'http://localhost:8000'});self.env.start()
        self.app=App(self.temp.name+'/test.db',[ROLE],self.ai,self.cu,False);self.cookie=''
    def tearDown(self):self.env.stop();self.temp.cleanup()
    def req(self,path,body=None,method=None,cookie=None,origin='http://localhost:8000',raw=False):
        method=method or ('POST' if body is not None else 'GET');data=body if raw else json.dumps(body or {}).encode()
        env={'REQUEST_METHOD':method,'PATH_INFO':path,'REMOTE_ADDR':'127.0.0.1','CONTENT_TYPE':'audio/webm' if raw else 'application/json','CONTENT_LENGTH':str(len(data)),'wsgi.input':io.BytesIO(data),'HTTP_ORIGIN':origin,'HTTP_X_REQUESTED_WITH':'Flashspace','HTTP_COOKIE':self.cookie if cookie is None else cookie}
        result={}
        def start(status,headers): result.update(status=int(status.split()[0]),headers=dict(headers))
        out=b''.join(self.app(env,start));result['body']=json.loads(out) if out[:1] in (b'{',b'[',b'n') else out
        if 'Set-Cookie' in result['headers']:self.cookie=result['headers']['Set-Cookie'].split(';')[0]
        return result
    def register(self,email='candidate@example.com'):
        r=self.req('/api/register',{'name':'Test Candidate','email':email,'password':'CorrectHorse123!'});self.assertEqual(r['status'],200);return r
    def apply(self):
        r=self.req('/api/applications',{'role_id':'growth','experience':'I built a measurable partner onboarding workflow.','portfolio':'https://example.com/resume','consent':True});self.assertEqual(r['status'],200);return r['body']
    def complete(self):
        a=self.apply()
        for i in range(4):
            r=self.req(f"/api/applications/{a['id']}/answer",{'answer':f'I tracked adoption and tested improvement number {i}.','turn':i});self.assertEqual(r['status'],200)
        r=self.req(f"/api/applications/{a['id']}/finish",{});self.assertEqual(r['status'],200);return a
    def test_password_hash(self):
        v=hash_password('CorrectHorse123!');self.assertNotIn('CorrectHorse',v);self.assertTrue(verify_password('CorrectHorse123!',v));self.assertFalse(verify_password('wrong',v))
    def test_auth_cookie_and_logout(self):
        r=self.register();self.assertIn('HttpOnly',r['headers']['Set-Cookie']);self.assertIn('SameSite=Strict',r['headers']['Set-Cookie']);self.assertFalse(r['body']['admin']);self.assertEqual(self.req('/api/me')['body']['email'],'candidate@example.com');self.req('/api/logout',{});self.assertIsNone(self.req('/api/me')['body'])
    def test_login_persists(self):
        self.register();self.cookie='';self.assertEqual(self.req('/api/login',{'email':'candidate@example.com','password':'CorrectHorse123!'})['status'],200)
    def test_bad_password(self):
        self.register();self.assertEqual(self.req('/api/login',{'email':'candidate@example.com','password':'WrongPassword123!'})['status'],401)
    def test_public_roles_and_no_auth_leak(self):
        self.assertEqual(len(self.req('/api/roles')['body']),1);self.assertEqual(self.req('/api/applications')['status'],401)
    def test_unpublished_roles(self):
        self.app.roles=[{**ROLE,'published':False}];self.assertEqual(self.req('/api/roles')['body'],[])
    def test_csrf(self):
        self.assertEqual(self.req('/api/register',{'name':'Test','email':'test@example.com','password':'CorrectHorse123!'},origin='https://evil.example')['status'],403)
    def test_consent_required(self):
        self.register();self.assertEqual(self.req('/api/applications',{'role_id':'growth','experience':'I did a relevant project for this role.'})['status'],400)
    def test_duplicate_application(self):
        self.register();a=self.apply();b=self.apply();self.assertEqual(a['id'],b['id']);self.assertEqual(len(self.req('/api/applications')['body']),1)
    def test_cross_candidate_denied(self):
        self.register();a=self.apply();self.register('other@example.com');self.assertEqual(self.req(f"/api/applications/{a['id']}/answer",{'turn':0,'answer':'An unauthorized answer.'})['status'],404)
    def test_candidate_cannot_admin(self):
        self.register();self.assertEqual(self.req('/api/admin/applications')['status'],403)
    def test_full_interview_idempotency_and_score_privacy(self):
        self.register();a=self.complete();path=f"/api/applications/{a['id']}"
        self.assertEqual(self.req(path+'/answer',{'turn':3,'answer':'I tracked adoption and tested improvement number 3.'})['status'],200)
        self.assertEqual(self.req(path+'/finish',{})['status'],200)
        self.app.work_once();self.assertEqual(self.ai.questions,3);self.assertEqual(self.ai.evaluations,1)
        self.app.work_once();self.assertEqual(self.ai.evaluations,1)
        shown=self.req('/api/applications')['body'][0];self.assertNotIn('evaluation',shown);self.assertNotIn('task_url',shown);self.assertEqual(shown['sync_status'],'Synced');self.assertEqual(self.cu.records[-1]['evaluation']['score'],60)
    def test_early_finish_rejected(self):
        self.register();a=self.apply();self.assertEqual(self.req(f"/api/applications/{a['id']}/finish",{})['status'],409)
    def test_out_of_order_answer(self):
        self.register();a=self.apply();self.assertEqual(self.req(f"/api/applications/{a['id']}/answer",{'turn':2,'answer':'A sufficient but out of order answer.'})['status'],409)
    def test_provider_failure_preserves_progress(self):
        self.register();a=self.apply();self.ai.fail=True;r=self.req(f"/api/applications/{a['id']}/answer",{'turn':0,'answer':'I built an onboarding process.'});self.assertEqual(r['status'],502);self.assertEqual(self.req('/api/applications')['body'][0]['answers'],[])
    def test_report_failure_still_syncs_transcript(self):
        self.register();a=self.complete();self.ai.fail=True;self.app.work_once();self.assertEqual(len(self.cu.records[-1]['answers']),4);self.assertEqual(self.req('/api/applications')['body'][0]['sync_status'],'Retry pending')
    def test_clickup_failure_retry(self):
        self.register();a=self.apply();self.cu.fail=True;self.app.work_once();self.assertEqual(self.app.store.get(a['id'])['sync_status'],'Retry pending');self.cu.fail=False
        with self.app.store.db() as db:db.execute('UPDATE applications SET next_retry=0')
        self.app.work_once();self.assertEqual(self.app.store.get(a['id'])['sync_status'],'Synced')
    def test_audio_transport_and_ownership(self):
        self.register();a=self.apply();path=f"/api/applications/{a['id']}";self.assertEqual(self.req(path+'/transcribe',b'a'*101,raw=True)['status'],200);self.assertEqual(self.req(path+'/speech',{})['body'],b'fake-audio')
    def test_invalid_audio_and_payload(self):
        self.register();a=self.apply();self.assertEqual(self.req(f"/api/applications/{a['id']}/transcribe",b'a',raw=True)['status'],400);self.assertEqual(self.req(f"/api/applications/{a['id']}/answer",{'turn':0,'answer':10})['status'],400)
    def test_description_complete(self):
        self.register();a=self.complete();raw=self.app.store.get(a['id']);description=ClickUp.description(raw);self.assertIn('FULL INTERVIEW TRANSCRIPT',description);self.assertIn('Consent recorded:',description);self.assertIn('Question 4:',description)
    def test_resume_url_not_executed(self):
        self.register();self.assertEqual(self.req('/api/applications',{'role_id':'growth','experience':'I built a relevant onboarding workflow.','portfolio':'javascript:alert(1)','consent':True})['status'],400)
    def test_quota(self):
        self.app.store.quota('test',1)
        with self.assertRaises(APIError): self.app.store.quota('test',1)
    def test_bad_evidence_rejected(self):
        ai=AI();ai.structured=lambda *args:{'summary':'A summary.','criteria':[{'name':n,'score':3,'reason':'Evidence','evidence':'invented quote'} for n in ['Relevant experience','Problem solving','Evidence of impact']]}
        with self.assertRaises(APIError):ai.evaluate(ROLE,[{'answer':'The real answer.'}])
    def test_missing_evidence_zeroed(self):
        ai=AI();ai.structured=lambda *args:{'summary':'Limited evidence.','criteria':[{'name':n,'score':5,'reason':'No quote','evidence':''} for n in ['Relevant experience','Problem solving','Evidence of impact']]};self.assertEqual(ai.evaluate(ROLE,[{'answer':'A brief response.'}])['score'],0)
    def test_clickup_reconciles_existing_task(self):
        self.register();a=self.apply();record=self.app.store.get(a['id']);cu=ClickUp(self.app.store);calls=[]
        name=f"{record['name'][:60]} | {record['role_title'][:60]} | FS-{record['id']}"
        def call(method,path,data=None):
            calls.append((method,path));return {'tasks':[{'id':'existing','name':name,'url':'https://example.com/existing'}]} if method=='GET' else {'id':'existing','url':'https://example.com/existing'}
        cu.list_id=lambda role:'role-list';cu.call=call;cu.sync(record);self.assertEqual([c[0] for c in calls],['GET','PUT']);self.assertEqual(self.app.store.get(a['id'])['task_id'],'existing')
if __name__=='__main__':unittest.main()
