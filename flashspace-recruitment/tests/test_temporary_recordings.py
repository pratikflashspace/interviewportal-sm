import io
import json
import os
import tempfile
import unittest
from unittest.mock import patch
import test_backend as legacy
from backend.temporary_recordings import RecordingApp,TemporaryStore,MAX_FILE,APIError

class StoreTests(unittest.TestCase):
    def setUp(self):self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.s=TemporaryStore(self.temp.name)
    def test_ten_slots_and_no_eviction(self):
        ids=[self.s.create('a','u','video/webm')['id'] for _ in range(10)]
        with self.assertRaises(APIError):self.s.create('a','u','video/webm')
        self.assertEqual(len(self.s.all()),10);self.s.remove(ids[0]);self.s.create('a','u','video/webm');self.assertEqual(len(self.s.all()),10)
    def test_replay_and_conflicting_chunks(self):
        m=self.s.create('a','u','video/webm');data=b'\x1aE\xdf\xa3'+b'x'*100
        self.s.append(m['id'],0,data);self.s.append(m['id'],0,data)
        self.assertEqual(self.s.get(m['id'])['bytes'],len(data))
        with self.assertRaises(APIError):self.s.append(m['id'],0,b'wrong')
        with self.assertRaises(APIError):self.s.finish(m['id'],2)
        self.assertEqual(self.s.finish(m['id'],1)['status'],'ready')
        self.assertEqual(TemporaryStore(self.temp.name).get(m['id'])['status'],'ready')
    def test_limits_and_paths(self):
        with self.assertRaises(APIError):self.s.get('../secret')
        m=self.s.create('a','u','video/webm')
        with self.assertRaises(APIError):self.s.append(m['id'],0,b'not-video')
        with self.assertRaises(APIError):self.s.append(m['id'],0,b'x'*(1024*1024+1))

class RecordingTests(legacy.BackendTests):
    def setUp(self):
        super().setUp();self.app=RecordingApp(db_path=self.temp.name+'/test.db',roles=[legacy.ROLE],ai=self.ai,clickup=self.cu,start_worker=False,recording_root=self.temp.name+'/recordings')
    def test_unpublished_roles(self):
        self.app.role_repository.update('growth',{'version':1,'state':'draft'},'admin',True);self.assertEqual(self.req('/api/roles')['body'],[])
    def test_provider_failure_preserves_progress(self):
        self.register();a=self.apply();self.ai.fail=True
        result=self.req('/api/applications/'+a['id']+'/answer',{'turn':0,'answer':'A fictional sufficient answer.'})
        self.assertEqual(result['status'],200);self.assertEqual(len(result['body']['answers']),1)
    def test_recording_ownership_and_private_playback(self):
        self.register();a=self.apply()
        r=self.req('/api/recordings',{'application_id':a['id'],'mime':'video/webm','consent':'temporary-av-v1'})
        self.assertEqual(r['status'],200);rid=r['body']['id'];path='/api/recordings/'+rid
        data=b'\x1aE\xdf\xa3'+b'x'*100
        self.assertEqual(self.req(path+'/chunk/0',data,raw=True)['status'],200)
        self.assertEqual(self.req(path+'/finish',{'chunks':1})['status'],200)
        self.assertIn('/recordings?',self.app.store.get(a['id'])['recording_review_url'])
        self.assertEqual(self.req(path+'/media')['status'],403)
        cookie=self.cookie;self.register('other@example.com')
        self.assertEqual(self.req(path+'/chunk/1',b'x'*100,raw=True)['status'],404)
        self.assertEqual(self.req(path+'/media')['status'],404)
        self.cookie=cookie
        with self.app.store.db() as db:db.execute('UPDATE users SET admin=1 WHERE email=?',('candidate@example.com',))
        r=self.req(path+'/media');self.assertEqual(r['status'],200);self.assertEqual(r['body'],data)
        self.assertEqual(self.req(path+'/remove',{})['status'],200)
        self.assertEqual(self.req(path+'/media')['status'],404)
    def test_consent_and_csrf_required(self):
        self.register();a=self.apply()
        self.assertEqual(self.req('/api/recordings',{'application_id':a['id'],'mime':'video/webm'})['status'],400)
        self.assertEqual(self.req('/api/recordings',{'application_id':a['id'],'mime':'video/webm','consent':'temporary-av-v1'},origin='https://evil.example')['status'],403)
    def test_camera_header_same_origin_only(self):
        r=self.req('/api/health');self.assertEqual(r['headers']['Permissions-Policy'],'camera=(self), microphone=(self)')
