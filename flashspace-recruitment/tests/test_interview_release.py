import unittest
from test_integrated_recordings import IntegratedRecordingTests
from backend.interview_release import InterviewRelease
from backend.integrated_recordings import IntegratedApp
from unittest.mock import patch

class ReleaseTests(IntegratedRecordingTests):
    def setUp(self):
        super().setUp()
        self.app=InterviewRelease(db_path=self.temp.name+'/test.db',roles=[],ai=self.ai,clickup=self.cu,start_worker=False,recording_root=self.temp.name+'/recordings')
    def test_abort_releases_active_capture_but_keeps_slot(self):
        m=self.capture()['body'];url='/api/recordings/'+m['id']+'/abort'
        self.assertEqual(self.req(url,{})['status'],200)
        self.assertEqual(self.app.recordings.get(m['id'])['status'],'incomplete')
        self.assertEqual(self.capture()['status'],200)
        self.assertEqual(len(self.app.recordings.all(self.aid)),2)
    def test_other_user_cannot_abort_or_list_capture(self):
        m=self.capture()['body'];self.register('another@example.com')
        self.assertEqual(self.req('/api/recordings/'+m['id']+'/abort',{})['status'],404)
        self.assertEqual(self.req('/api/v2/applications/'+self.aid+'/recordings')['status'],404)
    def test_continuation_before_next_question_delivery(self):
        question=self.f['active']['id'];body={'event_id':'unique-event-001','question_id':question,'version':0,'answer':'I coordinated a project.'}
        f=self.req('/api/v2/applications/'+self.aid+'/answer',body)['body']
        result=self.req('/api/v2/applications/'+self.aid+'/continuation',{'event_id':body['event_id'],'version':f['version'],'answer':body['answer']+' I measured its impact.'})
        self.assertEqual(result['status'],200,result['body'])
        self.assertEqual(len(result['body']['answers']),1)
        self.assertIn('measured',self.app.store.get(self.aid)['answers'][0]['answer'])
        self.app.playback.reserve(self.aid,result['body']['active']['id'])
        self.assertEqual(self.req('/api/v2/applications/'+self.aid+'/continuation',{'event_id':body['event_id'],'version':result['body']['version'],'answer':body['answer']+' Another update.'})['status'],409)
    def test_continuation_cannot_replace_existing_evidence(self):
        f=self.req('/api/v2/applications/'+self.aid+'/answer',{'event_id':'unique-event-001','question_id':self.f['active']['id'],'version':0,'answer':'Original evidence.'})['body']
        self.assertEqual(self.req('/api/v2/applications/'+self.aid+'/continuation',{'event_id':'unique-event-001','version':f['version'],'answer':'Replacement evidence.'})['status'],400)
