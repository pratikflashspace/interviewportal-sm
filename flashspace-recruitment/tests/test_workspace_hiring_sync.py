"""Real workspace/worker paths; ClickUp network boundary mocked, no live writes."""
import json
from contextlib import contextmanager
from unittest.mock import patch
import test_workspace_server as ws
from backend.server import APIError
from backend.workspace_hiring_sync import WorkspaceClickUp

class HiringSyncTests(ws.WorkspaceTests):
    def prepare(self):
        self.signup()
        r=self.req('/api/applications',{'role_id':'growth','experience':'Synthetic hiring sync application.','consent':True})
        self.assertEqual(r['status'],200,r);aid=r['body']['id']
        a=self.app.store.get(aid);a['status']='completed'
        a['answers']=[{'question':'Synthetic question','answer':'Synthetic preserved answer','at':'test'}]
        a['evaluation']={'summary':'Synthetic preserved report','score':None,'model':'fake','rubric_version':'test','criteria':[]}
        a['recording_review_url']='https://test.example/interview-review?application='+aid
        self.app.store.save(a)
        with self.app.store.db() as db:
            db.execute('UPDATE applications SET task_id=?,task_url=?,synced_version=version WHERE id=?',('existing-test-task','https://example.com/task',aid))
        self.recruiter();self.login_recruiter();self.app.job_wakeup.clear()
        self.assertIsInstance(self.app.clickup,WorkspaceClickUp)
        self.app.clickup.list_id=lambda role:'test-list'
        self.calls=[]
        def call(method,path,data=None):
            self.calls.append((method,path,data));return {'id':'existing-test-task','url':'https://example.com/task'}
        self.app.clickup.call=call
        return aid

    def move(self,aid,stage='shortlisted',version=0):
        return self.req('/api/workspace/recruiter/applications/'+aid+'/stage',{'stage':stage,'version':version})

    def test_decision_queues_and_syncs_existing_task_without_changing_interview(self):
        aid=self.prepare();before=self.app.store.get(aid)
        self.assertEqual(self.move(aid)['status'],200)
        after=self.app.store.get(aid)
        self.assertEqual(after['version'],before['version']+1);self.assertEqual(after['sync_status'],'Queued')
        self.assertTrue(self.app.job_wakeup.is_set())
        for key in ('status','answers','evaluation','task_id','recording_review_url'):self.assertEqual(after[key],before[key])
        self.app.work_once()
        self.assertEqual(self.app.store.get(aid)['sync_status'],'Synced')
        self.assertEqual(len(self.calls),1);method,path,payload=self.calls[0]
        self.assertEqual((method,path),('PUT','task/existing-test-task'))
        for text in ('Current hiring stage: Shortlisted','Synthetic preserved answer','Synthetic preserved report','INTERVIEW RECORDING'):
            self.assertIn(text,payload['description'])
        self.assertNotIn('actor',payload['description']);self.assertNotIn('status',payload)

    def test_network_failure_then_retry_preserves_decision(self):
        aid=self.prepare();self.move(aid)
        success=self.app.clickup.call
        self.app.clickup.call=lambda *args:(_ for _ in ()).throw(APIError(502,'Synthetic upstream failure'))
        self.app.work_once();self.assertEqual(self.app.store.get(aid)['sync_status'],'Retry pending')
        self.assertEqual(self.app.tracking(self.app.store.get(aid))['stage'],'shortlisted')
        self.app.clickup.call=success
        with self.app.store.db() as db:db.execute('UPDATE applications SET next_retry=0 WHERE id=?',(aid,))
        self.app.work_once();self.assertEqual(self.app.store.get(aid)['sync_status'],'Synced')
        self.assertEqual(len(self.calls),1)

    def test_stale_decision_does_not_duplicate_event_or_queue(self):
        aid=self.prepare();self.move(aid);self.app.work_once();before=self.app.store.get(aid)
        self.assertEqual(self.move(aid,'hired',0)['status'],409)
        after=self.app.store.get(aid);self.assertEqual(after['version'],before['version']);self.assertEqual(after['sync_status'],'Synced')
        self.assertEqual(len(self.app.tracking(after)['events']),1)

    def test_stage_audit_and_queue_roll_back_together(self):
        aid=self.prepare();before=self.app.store.get(aid);original=self.app.store.db
        class FailQueue:
            def __init__(self,db):self.db=db
            def execute(self,sql,params=()):
                if sql.startswith('UPDATE applications SET version=version+1'):raise RuntimeError('Synthetic queue write failure')
                return self.db.execute(sql,params)
        @contextmanager
        def broken():
            with original() as db:yield FailQueue(db)
        with patch.object(self.app.store,'db',broken):self.assertEqual(self.move(aid)['status'],500)
        after=self.app.store.get(aid)
        self.assertEqual(after['version'],before['version']);self.assertEqual(after['sync_status'],'Synced')
        self.assertEqual(self.app.tracking(after)['events'],[])
        self.assertEqual(self.app.record('application:'+aid,{})['version'],0)

    def test_new_decision_during_sync_remains_queued(self):
        aid=self.prepare();self.move(aid);original=self.app.clickup.call
        def delayed(method,path,data=None):
            result=original(method,path,data)
            self.assertEqual(self.move(aid,'hired',1)['status'],200)
            self.app.clickup.call=original
            return result
        self.app.clickup.call=delayed;self.app.work_once()
        self.assertEqual(self.app.store.get(aid)['sync_status'],'Queued')
        self.app.work_once();self.assertEqual(self.app.store.get(aid)['sync_status'],'Synced')
        self.assertIn('Current hiring stage: Hired',self.calls[-1][2]['description'])
        self.assertEqual(len(self.calls),2)

    def test_invalid_stage_payload_rejected(self):
        aid=self.prepare()
        for stage,version in (([],0),('shortlisted',-1),('shortlisted',True),('unapproved',0)):
            self.assertEqual(self.move(aid,stage,version)['status'],400)
        self.assertEqual(self.app.store.get(aid)['sync_status'],'Synced')

    def test_no_decision_keeps_existing_description(self):
        aid=self.prepare()
        self.assertNotIn('RECRUITER HIRING DECISION',self.app.clickup.description(self.app.store.get(aid)))
