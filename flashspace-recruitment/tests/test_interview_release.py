import unittest
from test_integrated_recordings import IntegratedRecordingTests
from backend.interview_release import InterviewRelease
from backend.integrated_recordings import IntegratedApp
from unittest.mock import patch

class ReleaseTests(IntegratedRecordingTests):
    def setUp(self):
        super().setUp()
        self.app=InterviewRelease(db_path=self.temp.name+'/test.db',roles=[],ai=self.ai,clickup=self.cu,start_worker=False,recording_root=self.temp.name+'/recordings')
    def test_abort_only_touches_historic_incomplete_recordings(self):
        m=self.app.recordings.create_legacy(self.aid,self.uid(),'video/webm')
        self.assertEqual(self.req('/api/recordings/'+m['id']+'/abort',{})['status'],200)
        self.assertEqual(self.app.recordings.get(m['id'])['status'],'incomplete')
    def test_abort_requires_ownership(self):
        m=self.app.recordings.create_legacy(self.aid,self.uid(),'video/webm')
        self.register('another@example.com')
        self.assertEqual(self.req('/api/recordings/'+m['id']+'/abort',{})['status'],404)
    def test_new_capture_refused_on_release_app(self):
        self.assertEqual(self.attempt()['status'],409)
    def test_owner_can_list_own_historic_recordings(self):
        m=self.app.recordings.create_legacy(self.aid,self.uid(),'video/webm')
        rows=self.req('/api/v2/applications/'+self.aid+'/recordings')['body']['recordings']
        self.assertEqual([r['id'] for r in rows],[m['id']])
        self.register('other@example.com')
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

if __name__=='__main__':unittest.main()
