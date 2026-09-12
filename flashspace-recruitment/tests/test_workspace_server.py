"""Real WSGI requests against isolated SQLite; never external services."""
import io
import json
import os
import tempfile
import unittest
from unittest.mock import patch
from backend.workspace_server import WorkspaceApp, RECRUITER_EMAIL
from backend.server import hash_password, now
from test_backend import FakeAI, ROLE

class WorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.env=patch.dict(os.environ,{'APP_ORIGIN':'https://test.example'})
        self.env.start();self.addCleanup(self.env.stop)
        self.app=WorkspaceApp(db_path=self.tmp.name+'/test.db',roles=[ROLE],ai=FakeAI(),start_worker=False,recording_root=self.tmp.name+'/recordings')
        self.cookie=''
    def req(self,path,body=None,cookie=None,origin=None):
        raw=json.dumps(body).encode() if body is not None else b'';result={}
        env={'PATH_INFO':path,'REQUEST_METHOD':'POST' if body is not None else 'GET','HTTP_ORIGIN':origin or self.app.origin,'HTTP_X_REQUESTED_WITH':'Flashspace','CONTENT_TYPE':'application/json','CONTENT_LENGTH':str(len(raw)),'wsgi.input':io.BytesIO(raw),'HTTP_COOKIE':self.cookie if cookie is None else cookie,'REMOTE_ADDR':'synthetic'}
        def start(status,headers):result['status']=int(status.split()[0]);result['headers']=headers
        result['body']=json.loads(b''.join(self.app(env,start)))
        for k,v in result['headers']:
            if k=='Set-Cookie':self.cookie=v.split(';')[0]
        return result
    def signup(self,email='candidate@example.com'):
        return self.req('/api/auth/candidate/signup',{'name':'Test Candidate','email':email,'password':'test-password-long','confirm_password':'test-password-long'})
    def recruiter(self):
        with self.app.store.db() as db:
            db.execute('INSERT INTO users VALUES (?,?,?,?,1,?)',('recruiter',RECRUITER_EMAIL,'Recruiter',hash_password('test-password-long'),now()))
        return {'id':'recruiter','email':RECRUITER_EMAIL,'name':'Recruiter','admin':1}
    def login_recruiter(self):
        return self.req('/api/auth/recruiter/login',{'email':RECRUITER_EMAIL,'password':'test-password-long'})
    def test_candidate_signup_and_own_profile_persist(self):
        r=self.signup();self.assertEqual(r['status'],200,r)
        self.assertTrue(self.cookie.startswith('tr_session='))
        p=self.req('/api/workspace/profile')['body']
        r=self.req('/api/workspace/profile',{'version':p['version'],'fields':{'name':'Updated Candidate','skills':'Python, APIs','resume_url':'https://example.com/resume'}})
        self.assertEqual(r['status'],200,r)
        self.assertEqual(self.req('/api/workspace/profile')['body']['fields']['skills'],'Python, APIs')
        self.assertEqual(self.req('/api/me')['body']['name'],'Updated Candidate')
        self.assertEqual(self.req('/api/workspace/profile',{'version':0,'fields':{'name':'Stale'}})['status'],409)
    def test_candidate_cannot_change_role_email_or_another_profile(self):
        self.signup()
        for fields in ({'admin':1},{'role':'recruiter'},{'email':RECRUITER_EMAIL},{'user_id':'recruiter'}):
            self.assertEqual(self.req('/api/workspace/profile',{'version':0,'fields':fields})['status'],400)
        self.assertEqual(self.req('/api/admin/roles')['status'],403)
        self.assertEqual(self.req('/api/admin/applications')['status'],403)
    def test_normalized_email_unique_across_roles(self):
        self.recruiter()
        self.assertEqual(self.signup(RECRUITER_EMAIL.upper())['status'],409)
        self.assertEqual(self.signup()['status'],200)
        self.assertEqual(self.signup('CANDIDATE@example.com')['status'],409)
    def test_recruiter_signup_google_and_candidate_promotion_blocked(self):
        for path in ('/api/auth/recruiter/signup','/api/auth/recruiter/google'):
            self.assertEqual(self.req(path,{})['status'],404)
        self.assertEqual(self.req('/api/auth/candidate/signup',{'name':'Test','email':'test@example.com','password':'test-password-long','confirm_password':'test-password-long','admin':1})['status'],400)
    def test_role_login_not_guessed_and_recruiter_mfa_deferred(self):
        self.signup();self.recruiter()
        self.assertEqual(self.req('/api/auth/recruiter/login',{'email':'candidate@example.com','password':'test-password-long'})['status'],401)
        self.assertEqual(self.req('/api/auth/candidate/login',{'email':RECRUITER_EMAIL,'password':'test-password-long'})['status'],401)
        result=self.login_recruiter();self.assertEqual(result['status'],200,result)
        self.assertEqual(result['body']['role'],'recruiter')
        self.assertTrue(any(k=='Set-Cookie' for k,v in result['headers']))
    def test_legacy_login_cookie_and_csrf_rejected(self):
        self.signup();candidate_cookie=self.cookie
        self.assertEqual(self.req('/api/workspace/profile',cookie=candidate_cookie.replace('tr_session','fs_session'))['status'],401)
        self.assertEqual(self.req('/api/login',{})['status'],410)
        self.assertEqual(self.req('/api/register',{})['status'],410)
        self.assertEqual(self.req('/api/workspace/profile',{'version':0,'fields':{'name':'Wrong Origin'}},origin='https://wrong.example')['status'],403)
    def test_recruiter_profile_is_role_specific_and_candidate_api_denied(self):
        self.recruiter();self.login_recruiter()
        self.assertEqual(self.req('/api/workspace/profile')['body']['role'],'recruiter')
        self.assertEqual(self.req('/api/workspace/profile',{'version':0,'fields':{'designation':'Hiring Lead'}})['status'],200)
        self.assertEqual(self.req('/api/applications')['status'],403)
        self.assertEqual(self.req('/api/v2/roles')['status'],403)
        self.assertEqual(self.req('/api/workspace/profile',{'version':1,'fields':{'skills':'forbidden'}})['status'],400)
    def test_profile_isolation_logout_and_empty_recommendations(self):
        self.signup();first=self.cookie
        self.req('/api/workspace/profile',{'version':0,'fields':{'summary':'Only first candidate'}})
        self.assertEqual(self.req('/api/workspace/candidate/recommendations')['body'],[])
        self.signup('second@example.com')
        self.assertEqual(self.req('/api/workspace/profile')['body']['fields']['summary'],'')
        self.req('/api/logout',{})
        self.assertEqual(self.req('/api/workspace/profile')['status'],401)
        self.assertEqual(self.req('/api/workspace/profile',cookie=first)['body']['fields']['summary'],'Only first candidate')
    def test_no_automatic_recruiter_provisioning(self):
        with self.app.store.db() as db:self.assertEqual(db.execute('SELECT COUNT(*) AS n FROM users WHERE admin=1').fetchone()['n'],0)
    def test_reserved_email_without_account_and_wrong_admin(self):
        self.assertEqual(self.signup(RECRUITER_EMAIL)['status'],409)
        self.assertEqual(self.login_recruiter()['status'],401)
        with self.app.store.db() as db:db.execute('INSERT INTO users VALUES (?,?,?,?,1,?)',('other','other@example.com','Other',hash_password('test-password-long'),now()))
        self.assertEqual(self.req('/api/auth/recruiter/login',{'email':'other@example.com','password':'test-password-long'})['status'],401)
    def test_settings_persist_and_reject_privilege_fields(self):
        self.signup()
        r=self.req('/api/workspace/settings',{'version':0,'fields':{'work_mode':'remote','preferred_location':'Delhi'}})
        self.assertEqual(r['status'],200,r)
        self.assertEqual(self.req('/api/workspace/settings')['body']['fields']['work_mode'],'remote')
        self.assertEqual(self.req('/api/workspace/settings',{'version':0,'fields':{'work_mode':'onsite'}})['status'],409)
        self.assertEqual(self.req('/api/workspace/settings',{'version':1,'fields':{'admin':'1'}})['status'],400)
    def test_password_change_revokes_all_sessions(self):
        self.signup();old=self.cookie
        self.req('/api/auth/candidate/login',{'email':'candidate@example.com','password':'test-password-long'});second=self.cookie
        self.assertEqual(self.req('/api/workspace/password',{'current_password':'wrong-password','password':'another-test-password','confirm_password':'another-test-password'})['status'],401)
        r=self.req('/api/workspace/password',{'current_password':'test-password-long','password':'another-test-password','confirm_password':'another-test-password'})
        self.assertEqual(r['status'],200,r)
        self.assertEqual(self.req('/api/workspace/profile',cookie=old)['status'],401)
        self.assertEqual(self.req('/api/workspace/profile',cookie=second)['status'],401)
        self.assertEqual(self.req('/api/auth/candidate/login',{'email':'candidate@example.com','password':'another-test-password'})['status'],200)
    def test_support_ownership_and_recruiter_reply(self):
        self.signup();first=self.cookie
        r=self.req('/api/workspace/support',{'subject':'Audio issue','message':'Synthetic support ticket for testing'})
        self.assertEqual(r['status'],200,r);tid=r['body']['id']
        self.signup('second@example.com');self.assertEqual(self.req('/api/workspace/support')['body'],[])
        self.assertEqual(self.req('/api/workspace/recruiter/support/'+tid,{'reply':'bad','status':'resolved'})['status'],403)
        self.recruiter();self.login_recruiter()
        self.assertEqual(self.req('/api/workspace/recruiter/support/'+tid,{'reply':'Please check microphone permissions.','status':'resolved'})['status'],200)
        self.assertEqual(self.req('/api/workspace/support',cookie=first)['body'][0]['status'],'resolved')
    def test_company_and_analytics_permissions_and_empty_values(self):
        self.signup()
        for p in ('company','analytics','candidates','applications','support'):
            self.assertEqual(self.req('/api/workspace/recruiter/'+p)['status'],403)
        self.recruiter();self.login_recruiter()
        r=self.req('/api/workspace/recruiter/company',{'version':0,'fields':{'website':'https://example.com','description':'Synthetic company profile'}})
        self.assertEqual(r['status'],200,r)
        self.assertEqual(self.req('/api/workspace/recruiter/company')['body']['fields']['description'],'Synthetic company profile')
        r=self.req('/api/workspace/recruiter/analytics')['body'];self.assertEqual(r['applications'],0);self.assertIsNone(r['completion_rate'])
    def test_application_tracking_preserves_answers_and_human_stages(self):
        self.signup();candidate=self.cookie
        r=self.req('/api/applications',{'role_id':ROLE['id'],'experience':'Synthetic application experience','consent':True})
        self.assertEqual(r['status'],200,r);aid=r['body']['id']
        a=self.app.store.get(aid);a['status']='completed';self.app.store.save(a)
        self.recruiter();self.login_recruiter()
        r=self.req('/api/workspace/recruiter/applications/'+aid+'/stage',{'version':0,'stage':'shortlisted'})
        self.assertEqual(r['status'],200,r)
        self.assertEqual(self.req('/api/workspace/recruiter/applications/'+aid+'/stage',{'version':0,'stage':'hired'})['status'],409)
        self.assertEqual(self.app.store.get(aid)['status'],'completed')
        r=self.req('/api/workspace/candidate/applications',cookie=candidate)['body'][0]
        self.assertEqual(r['stage'],'shortlisted');self.assertEqual(len(r['events']),1)
        self.assertNotIn('actor',r['events'][0]);self.assertNotIn('evaluation',r)
        self.assertEqual(self.req('/api/workspace/recruiter/candidates')['body'][0]['applications'][0]['id'],aid)
        analytics=self.req('/api/workspace/recruiter/analytics')['body'];self.assertEqual(analytics['stages']['shortlisted'],1)

if __name__=='__main__':unittest.main()
