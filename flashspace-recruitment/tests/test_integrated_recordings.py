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
    def capture(self):
        return self.req('/api/v2/applications/'+self.aid+'/recording',{'mime':'video/webm','consent':'integrated-interview-av-v1'})
    def test_bound_to_current_application_and_requires_consent(self):
        self.assertEqual(self.req('/api/v2/applications/'+self.aid+'/recording',{'mime':'video/webm'})['status'],400)
        result=self.capture();self.assertEqual(result['status'],200,result['body'])
        self.assertEqual(result['body']['application_id'],self.aid)
        self.assertEqual(self.capture()['status'],409)
    def test_owner_upload_and_recruiter_only_review(self):
        result=self.capture();rid=result['body']['id'];prefix='/api/recordings/'+rid
        data=b'\x1aE\xdf\xa3'+b'x'*200
        self.assertEqual(self.req(prefix+'/chunk/0',data,raw=True)['status'],200)
        self.assertEqual(self.req(prefix+'/finish',{'chunks':1})['status'],200)
        a=self.app.store.get(self.aid)
        self.assertIn('/interview-review?application='+self.aid,a['recording_review_url'])
        self.assertIn(a['recording_review_url'],InterviewRecordingClickUp.description(a))
        self.assertEqual(self.req(prefix+'/media')['status'],403)
        self.assertEqual(self.req('/api/admin/applications/'+self.aid+'/recordings')['status'],403)
        cookie=self.cookie;self.register('other@example.com')
        self.assertEqual(self.req(prefix+'/chunk/1',b'x'*100,raw=True)['status'],404)
        self.assertEqual(self.capture()['status'],404)
        self.cookie=cookie
        with self.app.store.db() as db:db.execute('UPDATE users SET admin=1 WHERE email=?',('candidate@example.com',))
        self.assertEqual(self.req(prefix+'/media')['body'],data)
        rows=self.req('/api/admin/applications/'+self.aid+'/recordings')['body']['recordings']
        self.assertEqual(len(rows),1);self.assertNotIn('owner',rows[0]);self.assertNotIn('chunks',rows[0])
    def test_no_standalone_start_endpoint(self):
        self.assertEqual(self.req('/api/recordings',{'application_id':self.aid,'mime':'video/webm','consent':'temporary-av-v1'})['status'],404)
    def test_rejects_completed_interview_capture(self):
        f=self.app.flow(self.aid);f['status']='completed';f['active']=None
        self.app.save_flow(self.app.store.get(self.aid),f)
        self.assertEqual(self.capture()['status'],409)
    def test_count_cap_includes_unfinished_and_never_evicts(self):
        for n in range(10):self.app.recordings.create('a'+str(n),'u','video/webm')
        self.assertEqual(self.capture()['status'],409)
    def test_upload_csrf_and_chunk_replay(self):
        rid=self.capture()['body']['id'];path='/api/recordings/'+rid+'/chunk/0';data=b'\x1aE\xdf\xa3'+b'x'*20
        self.assertEqual(self.req(path,data,raw=True,origin='https://evil.example')['status'],403)
        self.assertEqual(self.req(path,data,raw=True)['status'],200)
        self.assertEqual(self.req(path,data,raw=True)['status'],200)
        self.assertEqual(self.app.recordings.get(rid)['bytes'],len(data))
    def test_camera_policy_and_v2_metadata(self):
        self.assertEqual(self.req('/api/health')['headers']['Permissions-Policy'],'camera=(self), microphone=(self)')
        apps=self.req('/api/applications')['body'];self.assertEqual(apps[0]['flow_version'],2)
        self.assertIn(self.aid,apps[0]['interview_url'])
    def test_private_range_requests(self):
        rid=self.capture()['body']['id'];data=b'\x1aE\xdf\xa3'+bytes(range(128))
        self.app.recordings.append(rid,0,data);self.app.recordings.finish(rid,1)
        with self.app.store.db() as db:db.execute('UPDATE users SET admin=1')
        env={'REQUEST_METHOD':'GET','PATH_INFO':'/api/recordings/'+rid+'/media','HTTP_COOKIE':self.cookie,'HTTP_RANGE':'bytes=4-12'}
        result={};body=b''.join(self.app(env,lambda s,h:result.update(status=s,headers=dict(h))))
        self.assertTrue(result['status'].startswith('206'));self.assertEqual(body,data[4:13])

class CaptureJavascriptTests(unittest.TestCase):
    def test_capture_lifecycle(self):
        if not shutil.which('node'):self.skipTest('Node unavailable')
        path=Path(__file__).resolve().parents[1]/'web/src/v2/interview-capture.test.mjs'
        result=subprocess.run(['node','--test',str(path)],capture_output=True,text=True,timeout=20)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
