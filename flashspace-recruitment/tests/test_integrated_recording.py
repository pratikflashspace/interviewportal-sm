import unittest
from pathlib import Path
from backend.integrated_recording import IntegratedApp
from test_temporary_recordings import RecordingTests
import test_backend as legacy

class IntegratedTests(RecordingTests):
    def setUp(self):
        super().setUp()
        self.app=IntegratedApp(db_path=self.temp.name+'/test.db',roles=[legacy.ROLE],ai=self.ai,clickup=self.cu,start_worker=False,recording_root=self.temp.name+'/integrated')
    def test_only_one_open_segment_per_application(self):
        self.register();a=self.apply();body={'application_id':a['id'],'mime':'video/webm','consent':'temporary-av-v1'}
        self.assertEqual(self.req('/api/recordings',body)['status'],200)
        self.assertEqual(self.req('/api/recordings',body)['status'],409)
    def test_completed_interview_cannot_start_arbitrary_recording(self):
        self.register();a=self.complete()
        self.assertEqual(self.req('/api/recordings',{'application_id':a['id'],'mime':'video/webm','consent':'temporary-av-v1'})['status'],409)
    def test_recording_review_scoped_to_application(self):
        self.register();a=self.apply();m=self.app.recordings.create(a['id'],self.app.store.get(a['id'])['user_id'],'video/webm')
        self.app.recordings.create('other-app','other','video/webm')
        path='/api/applications/'+a['id']+'/recordings'
        self.assertEqual(self.req(path)['status'],403)
        with self.app.store.db() as db:db.execute('UPDATE users SET admin=1')
        result=self.req(path);self.assertEqual(result['status'],200)
        self.assertEqual([r['id'] for r in result['body']['recordings']],[m['id']])
    def test_initial_speech_and_two_replays(self):
        self.register();a=self.apply();path='/api/applications/'+a['id']+'/speech'
        for _ in range(3):self.assertEqual(self.req(path,{})['status'],200)
        self.assertEqual(self.req(path,{})['status'],429)
    def test_finish_link_is_application_scoped(self):
        self.register();a=self.apply();uid=self.app.store.get(a['id'])['user_id'];m=self.app.recordings.create(a['id'],uid,'video/webm')
        self.app.recordings.append(m['id'],0,b'\x1aE\xdf\xa3'+b'x'*100)
        self.assertEqual(self.req('/api/recordings/'+m['id']+'/finish',{'chunks':1})['status'],200)
        self.assertTrue(self.app.store.get(a['id'])['recording_review_url'].endswith('/recordings?application='+a['id']))
    def test_no_floating_recorder_in_bootstrap(self):
        root=Path(__file__).resolve().parents[1]/'web/src'
        self.assertNotIn('RecordingDock',(root/'main.jsx').read_text())
        components=(root/'generated/components.jsx').read_text()
        self.assertIn("export {default as Interview} from '../IntegratedInterview.jsx'",components)
        self.assertIn('InterviewRecordingReview applicationId={report.id}',components)

class MediaNodeTests(unittest.TestCase):
    def test_media_lifecycle(self):
        import subprocess,shutil
        if not shutil.which('node'):self.skipTest('Node unavailable')
        file=Path(__file__).resolve().parents[1]/'web/src/interview-media.test.mjs'
        result=subprocess.run(['node','--test',str(file)],capture_output=True,text=True,timeout=20)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
