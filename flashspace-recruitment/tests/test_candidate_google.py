"""Synthetic WSGI + signed JWT tests. Never call Google or a real database."""
import io
import json
import os
import time
import tempfile
import unittest
from http.cookies import SimpleCookie
from unittest.mock import patch
from backend.candidate_google import WorkspaceApp, BASE, COOKIE, CLIENT_ID, verify_google_credential
from backend.server import APIError, hash_password, now
from test_backend import FakeAI, ROLE

class GoogleTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        p=patch.dict(os.environ, {'APP_ORIGIN':'https://test.example','TEAMRECRUT_CANDIDATE_GOOGLE_ENABLED':'true','GOOGLE_CLIENT_ID':CLIENT_ID,'TEAMRECRUT_GOOGLE_VERIFIED_ORIGIN':'https://test.example'})
        p.start();self.addCleanup(p.stop)
        self.app=WorkspaceApp(db_path=self.tmp.name+'/test.db',roles=[ROLE],ai=FakeAI(),start_worker=False,recording_root=self.tmp.name+'/recordings')
        self.cookies={}
        self.verifier=patch('backend.candidate_google.verify_google_credential').start();self.addCleanup(patch.stopall)
    def req(self,path,body=None,origin='https://test.example',cookie=None):
        raw=json.dumps(body).encode() if body is not None else b'';r={}
        env={'PATH_INFO':path,'REQUEST_METHOD':'POST' if body is not None else 'GET','HTTP_ORIGIN':origin,'HTTP_X_REQUESTED_WITH':'Flashspace','CONTENT_TYPE':'application/json','CONTENT_LENGTH':str(len(raw)),'wsgi.input':io.BytesIO(raw),'HTTP_COOKIE':cookie if cookie is not None else '; '.join(k+'='+v for k,v in self.cookies.items()),'REMOTE_ADDR':'synthetic'}
        def start(status,headers):r.update(status=int(status.split()[0]),headers=headers)
        data=b''.join(self.app(env,start))
        try:r['body']=json.loads(data)
        except ValueError:r['body']=data.decode()
        for key,value in r['headers']:
            if key.lower()=='set-cookie':
                c=SimpleCookie();c.load(value)
                for name,item in c.items():
                    if item['max-age']=='0':self.cookies.pop(name,None)
                    else:self.cookies[name]=item.value
        return r
    def prepare(self,**claims):
        r=self.req(BASE+'/challenge',{});self.assertEqual(r['status'],200,r)
        value={'sub':'synthetic-google-1','email':'synthetic.candidate@gmail.com','name':'Test Candidate','email_verified':True,'nonce':r['body']['nonce'],'iss':'https://accounts.google.com','aud':CLIENT_ID,'iat':int(time.time())-10,'exp':int(time.time())+300}
        value.update(claims);self.verifier.return_value=value
        return r
    def login(self,**body):return self.req(BASE,{'credential':'synthetic-token-not-a-real-jwt'*8,**body})
    def test_disabled_and_missing_config_fail_closed(self):
        for values in ({'TEAMRECRUT_CANDIDATE_GOOGLE_ENABLED':'false'},{'GOOGLE_CLIENT_ID':''},{'TEAMRECRUT_GOOGLE_VERIFIED_ORIGIN':'https://other.example'}):
            with self.subTest(values=values),patch.dict(os.environ,values):
                self.assertFalse(self.req(BASE+'/config')['body']['enabled'])
                self.assertEqual(self.req(BASE+'/challenge',{})['status'],503)
        self.verifier.assert_not_called()
    def test_signup_returns_candidate_and_persistent_identity(self):
        r=self.prepare();self.assertIn('HttpOnly',dict(r['headers'])['Set-Cookie']);self.assertIn('Secure',dict(r['headers'])['Set-Cookie'])
        result=self.login();self.assertEqual(result['status'],200,result);self.assertEqual(result['body']['role'],'candidate');self.assertFalse(result['body']['admin'])
        self.assertIn('tr_session',self.cookies);self.assertNotIn(COOKIE,self.cookies)
        self.assertEqual(self.req('/api/me')['body']['role'],'candidate')
        with self.app.store.db() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) AS n FROM candidate_google_identities').fetchone()['n'],1)
            u=dict(db.execute('SELECT * FROM users').fetchone());self.assertIn(':',u['password']);self.assertNotIn('credential',u)
        self.assertEqual(self.req('/api/admin/applications')['status'],403)
    def test_returning_subject_uses_same_user(self):
        self.prepare();self.assertEqual(self.login()['status'],200)
        self.req('/api/logout',{});self.prepare();self.assertEqual(self.login()['status'],200)
        with self.app.store.db() as db:self.assertEqual(db.execute('SELECT COUNT(*) AS n FROM users').fetchone()['n'],1)
    def test_no_manual_account_linking(self):
        self.req('/api/auth/candidate/signup',{'name':'Manual Candidate','email':'synthetic.candidate@gmail.com','password':'synthetic-password-long','confirm_password':'synthetic-password-long'})
        self.req('/api/logout',{});self.prepare();self.assertEqual(self.login()['status'],409)
        with self.app.store.db() as db:self.assertEqual(db.execute('SELECT COUNT(*) AS n FROM candidate_google_identities').fetchone()['n'],0)
    def test_reserved_recruiter_and_recruiter_google_denied(self):
        self.prepare(email='team@stirringminds.com',hd='stirringminds.com');self.assertEqual(self.login()['status'],403)
        self.assertEqual(self.req('/api/auth/recruiter/google',{})['status'],404)
        self.assertEqual(self.req('/api/auth/recruiter/signup',{})['status'],404)
    def test_existing_admin_other_email_cannot_be_linked(self):
        with self.app.store.db() as db:db.execute('INSERT INTO users VALUES (?,?,?,?,1,?)',('admin','synthetic.candidate@gmail.com','Admin',hash_password('synthetic-password-long'),now()))
        self.prepare();self.assertEqual(self.login()['status'],409)
    def test_csrf_and_missing_cookie_rejected_before_provider(self):
        self.assertEqual(self.req(BASE+'/challenge',{},origin='https://evil.example')['status'],403)
        self.prepare();self.assertEqual(self.req(BASE,{'credential':'x'*200},cookie='')['status'],401)
        self.verifier.assert_not_called()
    def test_expired_challenge_and_replay(self):
        self.prepare()
        with self.app.store.db() as db:db.execute('UPDATE candidate_google_challenges SET expires=0')
        self.assertEqual(self.login()['status'],401);self.verifier.assert_not_called()
        self.prepare(nonce='wrong-nonce');cookie='; '.join(k+'='+v for k,v in self.cookies.items())
        self.assertEqual(self.login()['status'],401)
        self.assertEqual(self.req(BASE,{'credential':'x'*200},cookie=cookie)['status'],401)
        self.assertEqual(self.verifier.call_count,1)
    def test_invalid_claims_rejected(self):
        cases=[{'iss':'evil'},{'aud':'other'},{'azp':'other'},{'exp':0},{'iat':time.time()+600},{'email_verified':False},{'email_verified':'true'},{'sub':''},{'email':'broken'},{'nonce':'wrong'}]
        for changes in cases:
            with self.subTest(changes=changes):self.prepare(**changes);self.assertEqual(self.login()['status'],401)
    def test_third_party_email_requires_manual_flow(self):
        self.prepare(email='candidate@example.com');self.assertEqual(self.login()['status'],409)
    def test_changed_subject_email_not_silently_updated(self):
        self.prepare();self.login();self.req('/api/logout',{})
        self.prepare(email='another.synthetic@gmail.com');self.assertEqual(self.login()['status'],403)
    def test_client_role_input_rejected(self):
        self.prepare();self.assertEqual(self.login(role='recruiter')['status'],400);self.verifier.assert_not_called()
    def test_provider_outage_no_session_and_nonce_consumed(self):
        self.prepare();self.verifier.side_effect=APIError(503,'Google unavailable')
        self.assertEqual(self.login()['status'],503);self.assertNotIn('tr_session',self.cookies)
        self.assertEqual(self.login()['status'],401)
    def test_active_session_cannot_switch_identity(self):
        self.prepare();self.login();self.assertEqual(self.req(BASE+'/challenge',{})['status'],409)
    def test_quota_prevents_provider_request(self):
        self.prepare()
        with self.app.store.db() as db:db.execute("UPDATE quotas SET n=20 WHERE key='google-auth-ip:synthetic'")
        self.assertEqual(self.login()['status'],429);self.verifier.assert_not_called()
    def test_manual_login_remains_available_when_google_disabled(self):
        with patch.dict(os.environ,{'TEAMRECRUT_CANDIDATE_GOOGLE_ENABLED':'false'}):
            r=self.req('/api/auth/candidate/signup',{'name':'Manual Candidate','email':'manual@example.com','password':'synthetic-password-long','confirm_password':'synthetic-password-long'})
            self.assertEqual(r['status'],200,r);self.req('/api/logout',{})
            self.assertEqual(self.req('/api/auth/candidate/login',{'email':'manual@example.com','password':'synthetic-password-long'})['status'],200)

class GoogleSignatureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import rsa
        from google.auth import crypt
        public,private=rsa.newkeys(2048)
        cls.public=public.save_pkcs1().decode()
        cls.signer=crypt.RSASigner.from_string(private.save_pkcs1(),key_id='synthetic-key')
    def token(self,**changes):
        from google.auth import jwt
        claims={'iss':'https://accounts.google.com','aud':CLIENT_ID,'sub':'test-sub','iat':int(time.time())-5,'exp':int(time.time())+300};claims.update(changes)
        return jwt.encode(self.signer,claims).decode()
    def test_real_signed_token_with_mock_google_public_keys(self):
        with patch('google.oauth2.id_token._fetch_certs',return_value={'synthetic-key':self.public}):
            self.assertEqual(verify_google_credential(self.token(),CLIENT_ID)['sub'],'test-sub')
    def test_real_verifier_rejects_wrong_audience_expiry_issuer_signature(self):
        valid=self.token();parts=valid.split('.');parts[2]=('A' if parts[2][0]!='A' else 'B')+parts[2][1:]
        for token in (self.token(aud='evil'),self.token(exp=1),self.token(iss='evil'),'.'.join(parts),'not.a.token'):
            with self.subTest(token_kind=token[:8]),patch('google.oauth2.id_token._fetch_certs',return_value={'synthetic-key':self.public}),self.assertRaises(APIError):
                verify_google_credential(token,CLIENT_ID)

if __name__=='__main__':unittest.main()
