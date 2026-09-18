import os,tempfile,unittest,subprocess,shutil
from pathlib import Path
from unittest.mock import patch
import test_workspace_server as fixture
from backend.candidate_account import WorkspaceApp
from backend.server import now
ROOT=Path(__file__).resolve().parents[1]
class AccountTests(unittest.TestCase):
 req=fixture.WorkspaceTests.req
 signup=fixture.WorkspaceTests.signup
 recruiter=fixture.WorkspaceTests.recruiter
 login_recruiter=fixture.WorkspaceTests.login_recruiter
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
  p=patch.dict(os.environ,{'APP_ORIGIN':'https://test.example','CLICKUP_API_TOKEN':''});p.start();self.addCleanup(p.stop)
  self.app=WorkspaceApp(db_path=self.tmp.name+'/a.db',roles=[fixture.ROLE],ai=fixture.FakeAI(),start_worker=False,recording_root=self.tmp.name+'/recordings');self.cookie=''
 def test_method_metadata_and_privacy(self):
  path='/api/workspace/candidate/account';self.assertEqual(self.req(path)['status'],401)
  self.signup();r=self.req(path);self.assertEqual(r['body'],{'email':'candidate@example.com','role':'candidate','auth_method':'password','password_change_allowed':True})
  self.assertEqual(self.req(path,{'email':'evil@example.com'})['status'],405)
  self.recruiter();self.login_recruiter();self.assertEqual(self.req(path)['status'],403)
 def test_password_change_revokes_all_sessions(self):
  self.signup();old=self.cookie
  self.req('/api/auth/candidate/login',{'email':'candidate@example.com','password':'test-password-long'});second=self.cookie
  body={'current_password':'wrong-password-long','password':'new-synthetic-password','confirm_password':'new-synthetic-password'}
  self.assertEqual(self.req('/api/workspace/password',body)['status'],401)
  body['current_password']='test-password-long';self.assertEqual(self.req('/api/workspace/password',body)['status'],200)
  for cookie in [old,second]:self.assertEqual(self.req('/api/workspace/candidate/account',cookie=cookie)['status'],401)
  self.assertEqual(self.req('/api/auth/candidate/login',{'email':'candidate@example.com','password':'new-synthetic-password'})['status'],200)
 def test_google_cannot_change_password_through_direct_endpoint(self):
  self.signup()
  with self.app.store.db() as db:
   user=db.execute('SELECT id FROM users WHERE email=?',('candidate@example.com',)).fetchone()
   db.execute('INSERT INTO candidate_google_identities VALUES (?,?,?)',('synthetic-google-subject',user['id'],now()))
  r=self.req('/api/workspace/candidate/account');self.assertFalse(r['body']['password_change_allowed']);self.assertEqual(r['body']['auth_method'],'google')
  self.assertEqual(self.req('/api/workspace/password',{'current_password':'test-password-long','password':'new-synthetic-password','confirm_password':'new-synthetic-password'})['status'],409)
 def test_support_persistence_reply_ownership_and_csrf(self):
  self.signup();first=self.cookie
  payload={'subject':'Synthetic help','message':'Synthetic support message for testing.'}
  self.assertEqual(self.req('/api/workspace/support',payload,origin='https://evil.example')['status'],403)
  r=self.req('/api/workspace/support',payload);self.assertEqual(r['status'],200);tid=r['body']['id']
  self.assertEqual(self.req('/api/workspace/support')['body'][0]['message'],payload['message'])
  self.signup('second@example.com');self.assertEqual(self.req('/api/workspace/support')['body'],[])
  self.recruiter();self.login_recruiter();self.assertEqual(self.req('/api/workspace/recruiter/support/'+tid,{'reply':'Synthetic reply','status':'resolved'})['status'],200)
  self.assertEqual(self.req('/api/workspace/support',cookie=first)['body'][0]['reply'],'Synthetic reply')
 def test_client(self):
  if not shutil.which('node'):self.skipTest('Node unavailable')
  r=subprocess.run(['node','--test',str(ROOT/'web/src/workspace/account-client.test.mjs')],capture_output=True,text=True,timeout=20);self.assertEqual(r.returncode,0,r.stdout+r.stderr)
