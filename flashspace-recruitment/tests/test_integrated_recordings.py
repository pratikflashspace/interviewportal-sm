import tempfile
import os
import unittest
import shutil
import subprocess
from pathlib import Path
from unittest.mock import patch
import test_backend as legacy
from test_v2_server import FakeV2,V2Tests
from backend.integrated_recordings import IntegratedApp,RecordingStore,InterviewRecordingClickUp
from backend.server import APIError

class IntegratedRecordingTests(unittest.TestCase):
    req=legacy.BackendTests.req
    register=legacy.BackendTests.register
    apply=legacy.BackendTests.apply
    new_v2=V2Tests.new_v2
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        env=patch.dict(os.environ,{'ADMIN_EMAIL':'','APP_ORIGIN':'http://localhost:8000'})
        env.start();self.addCleanup(env.stop)
        self.ai=FakeV2();self.cu=legacy.FakeClickUp();self.cookie=''
        self.app=IntegratedApp(db_path=self.temp.name+'/test.db',roles=[legacy.ROLE],ai=self.ai,clickup=self.cu,start_worker=False,recording_root=self.temp.name+'/recordings')
        with self.app.store.db() as db:db.execute('INSERT INTO settings(key,value) VALUES (?,?)',('v2-bank:growth','sales'))
        self.register();self.f=self.new_v2();self.aid=self.f['application_id']
    def attempt(self):
        return self.req('/api/v2/applications/'+self.aid+'/recording',{'mime':'video/webm','consent':'integrated-interview-av-v1'})
    def uid(self,email='candidate@example.com'):
        with self.app.store.db() as db:return db.execute('SELECT id FROM users WHERE email=?',(email,)).fetchone()[0]
    def test_new_capture_is_refused_but_route_is_owned_and_authenticated(self):
        result=self.attempt();self.assertEqual(result['status'],409,result['body'])
        self.assertIn('Voice-only',result['body']['error'])
    def test_capture_without_consent_is_refused(self):
        self.assertEqual(self.req('/api/v2/applications/'+self.aid+'/recording',{'mime':'video/webm'})['status'],409)
    def test_capture_requires_ownership(self):
        self.register('other@example.com')
        self.assertEqual(self.req('/api/v2/applications/'+self.aid+'/recording',{'mime':'video/webm','consent':'integrated-interview-av-v1'})['status'],404)
    def test_recruiter_review_route_remains(self):
        self.assertEqual(self.req('/api/admin/applications/'+self.aid+'/recordings')['status'],403)
        with self.app.store.db() as db:db.execute('UPDATE users SET admin=1 WHERE email=?',('candidate@example.com',))
        self.assertEqual(self.req('/api/admin/applications/'+self.aid+'/recordings')['body']['recordings'],[])
    def test_no_standalone_start_endpoint(self):
        self.assertEqual(self.req('/api/recordings',{'application_id':self.aid,'mime':'video/webm','consent':'temporary-av-v1'})['status'],404)
    def test_historic_recordings_stay_readable_and_private(self):
        m=self.app.recordings.create_legacy(self.aid,self.uid(),'video/webm')
        self.app.recordings.append(m['id'],0,b'\x1aE\xdf\xa3'+b'x'*200)
        self.app.recordings.finish(m['id'],1)
        self.assertEqual(self.req('/api/recordings/'+m['id']+'/media')['status'],403)
        owner_cookie=self.cookie
        self.register('other@example.com')
        self.assertEqual(self.req('/api/recordings/'+m['id']+'/media')['status'],403)
        self.cookie=owner_cookie
        with self.app.store.db() as db:db.execute('UPDATE users SET admin=1 WHERE email=?',('candidate@example.com',))
        self.assertEqual(self.req('/api/recordings/'+m['id']+'/media')['status'],200)
        rows=self.req('/api/admin/applications/'+self.aid+'/recordings')['body']['recordings']
        self.assertEqual(len(rows),1);self.assertNotIn('owner',rows[0]);self.assertNotIn('chunks',rows[0])
    def test_camera_policy_and_v2_metadata(self):
        self.assertEqual(self.req('/api/health')['headers']['Permissions-Policy'],'camera=(), microphone=(self)')
        apps=self.req('/api/applications')['body'];self.assertEqual(apps[0]['flow_version'],2)
        self.assertIn(self.aid,apps[0]['interview_url'])
    def test_private_range_requests(self):
        m=self.app.recordings.create_legacy(self.aid,self.uid(),'video/webm')
        data=b'\x1aE\xdf\xa3'+bytes(range(128))
        self.app.recordings.append(m['id'],0,data);self.app.recordings.finish(m['id'],1)
        with self.app.store.db() as db:db.execute('UPDATE users SET admin=1')
        env={'REQUEST_METHOD':'GET','PATH_INFO':'/api/recordings/'+m['id']+'/media','HTTP_COOKIE':self.cookie,'HTTP_RANGE':'bytes=4-12'}
        result={};body=b''.join(self.app(env,lambda s,h:result.update(status=s,headers=dict(h))))
        self.assertTrue(result['status'].startswith('206'));self.assertEqual(body,data[4:13])

class CaptureJavascriptTests(unittest.TestCase):
    def test_capture_lifecycle(self):
        if not shutil.which('node'):self.skipTest('Node unavailable')
        path=Path(__file__).resolve().parents[1]/'web/src/v2/interview-capture.test.mjs'
        result=subprocess.run(['node','--test',str(path)],capture_output=True,text=True,timeout=20)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)

if __name__=='__main__':unittest.main()
