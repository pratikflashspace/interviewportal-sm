"""Run real WSGI requests against isolated SQLite; never external services."""
import io
import json
import os
import tempfile
import unittest
from unittest.mock import patch
from backend.workspace_server import WorkspaceApp
from backend.server import hash_password, now
from test_backend import FakeAI, ROLE

class WorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.env=patch.dict(os.environ,{'TEAMRECRUT_RECRUITER_EMAIL':'recruiter@example.com','APP_ORIGIN':'https://test.example'})
        self.env.start();self.addCleanup(self.env.stop)
        self.app=WorkspaceApp(db_path=self.tmp.name+'/test.db',roles=[ROLE],ai=FakeAI(),start_worker=False,recording_root=self.tmp.name+'/recordings')
        self.cookie=''
    def req(self,path,body=None,cookie=None):
        raw=json.dumps(body).encode() if body is not None else b'';result={}
        env={'PATH_INFO':path,'REQUEST_METHOD':'POST' if body is not None else 'GET','HTTP_ORIGIN':self.app.origin,'HTTP_X_REQUESTED_WITH':'Flashspace','CONTENT_TYPE':'application/json','CONTENT_LENGTH':str(len(raw)),'wsgi.input':io.BytesIO(raw),'HTTP_COOKIE':self.cookie if cookie is None else cookie,'REMOTE_ADDR':'synthetic'}
        def start(status,headers):result['status']=int(status.split()[0]);result['headers']=headers
        result['body']=json.loads(b''.join(self.app(env,start)))
        for k,v in result['headers']:
            if k=='Set-Cookie':self.cookie=v.split(';')[0]
        return result
    def signup(self,email='candidate@example.com'):
        return self.req('/api/auth/candidate/signup',{'name':'Test Candidate','email':email,'password':'test-password-long','confirm_password':'test-password-long'})
    def recruiter(self):
        with self.app.store.db() as db:
            db.execute('INSERT INTO users VALUES (?,?,?,?,1,?)',('recruiter','recruiter@example.com','Recruiter',hash_password('test-password-long'),now()))
        return {'id':'recruiter','email':'recruiter@example.com','name':'Recruiter','admin':1}
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
        for fields in ({'admin':1},{'role':'recruiter'},{'email':'recruiter@example.com'},{'user_id':'recruiter'}):
            self.assertEqual(self.req('/api/workspace/profile',{'version':0,'fields':fields})['status'],400)
        self.assertEqual(self.req('/api/admin/roles')['status'],403)
        self.assertEqual(self.req('/api/admin/applications')['status'],403)
    def test_normalized_email_unique_across_roles(self):
        self.recruiter()
        self.assertEqual(self.signup('RECRUITER@example.com')['status'],409)
        self.assertEqual(self.signup()['status'],200)
        self.assertEqual(self.signup('CANDIDATE@example.com')['status'],409)
    def test_recruiter_signup_google_and_candidate_promotion_blocked(self):
        for path in ('/api/auth/recruiter/signup','/api/auth/recruiter/google'):
            self.assertEqual(self.req(path,{})['status'],404)
        self.assertEqual(self.req('/api/auth/candidate/signup',{'name':'Test','email':'test@example.com','password':'test-password-long','confirm_password':'test-password-long','admin':1})['status'],400)
    def test_role_login_not_guessed_and_mfa_fails_closed(self):
        self.signup();self.recruiter()
        self.assertEqual(self.req('/api/auth/recruiter/login',{'email':'candidate@example.com','password':'test-password-long'})['status'],401)
        self.assertEqual(self.req('/api/auth/candidate/login',{'email':'recruiter@example.com','password':'test-password-long'})['status'],401)
        result=self.req('/api/auth/recruiter/login',{'email':'recruiter@example.com','password':'test-password-long'})
        self.assertEqual(result['status'],503)
        self.assertFalse(any(k=='Set-Cookie' for k,v in result['headers']))
    def test_legacy_login_cookie_and_csrf_rejected(self):
        self.signup();candidate_cookie=self.cookie
        self.assertEqual(self.req('/api/workspace/profile',cookie=candidate_cookie.replace('tr_session','fs_session'))['status'],401)
        self.assertEqual(self.req('/api/login',{})['status'],410)
        self.assertEqual(self.req('/api/register',{})['status'],410)
    def test_recruiter_profile_is_role_specific_and_candidate_api_denied(self):
        u=self.recruiter();self.cookie=self.app.session(u)[1].split(';')[0]
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

if __name__=='__main__':unittest.main()
