"""Regression tests for the intermittent missing-report / stuck-Queued sync bug.

Bug: work_once() refused to mark a version synced when the AI report failed, so a
completed interview could show a synced transcript in ClickUp while the sync badge
stayed Queued/Retry-pending forever. Fix: transcript sync marks the version synced;
a failed report moves to an independent pending_reports retry lane that re-pushes
the report to the existing task without re-uploading the transcript.
"""
import json
import os
import tempfile
import unittest
from unittest.mock import patch
import test_backend as legacy
from backend.server import App, APIError
from backend.v2_server import InterviewV2App

ROLE=legacy.ROLE

class FlakyReportAI(legacy.FakeAI):
    """AI whose evaluation fails N times (like a Sarvam 502/quota blip), then works."""
    def __init__(self,failures):
        super().__init__();self.remaining=failures;self.attempts=0
    def evaluate(self,role,answers):
        self.attempts+=1
        if self.remaining>0:
            self.remaining-=1
            raise APIError(502,'Provider failed.')
        return {'summary':'Recovered report after retry.','score':None,'model':'fake','rubric_version':'test','criteria':[]}

class CountingClickUp(legacy.FakeClickUp):
    def __init__(self):
        super().__init__();self.syncs=0
    def sync(self,a):
        self.syncs+=1
        return super().sync(a)

class ReportRetryTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.env=patch.dict(os.environ,{'ADMIN_EMAIL':'','APP_ORIGIN':'http://localhost:8000','MAX_AI_CALLS_PER_DAY':'500'});self.env.start();self.addCleanup(self.env.stop)
        self.ai=FlakyReportAI(1);self.cu=CountingClickUp()
        self.app=App(self.temp.name+'/test.db',[ROLE],self.ai,self.cu,False);self.cookie=''
        self.registered=False
    def req(self,path,body=None,method=None,cookie=None,origin='http://localhost:8000',raw=False):
        method=method or ('POST' if body is not None else 'GET');data=body if raw else json.dumps(body or {}).encode()
        env={'REQUEST_METHOD':method,'PATH_INFO':path,'REMOTE_ADDR':'127.0.0.1','CONTENT_TYPE':'audio/webm' if raw else 'application/json','CONTENT_LENGTH':str(len(data)),'wsgi.input':__import__('io').BytesIO(data),'HTTP_ORIGIN':origin,'HTTP_X_REQUESTED_WITH':'Flashspace','HTTP_COOKIE':self.cookie if cookie is None else cookie}
        result={}
        def start(status,headers): result.update(status=int(status.split()[0]),headers=dict(headers))
        out=b''.join(self.app(env,start));result['body']=json.loads(out) if out[:1] in (b'{',b'[',b'n') else out
        if 'Set-Cookie' in result['headers']:self.cookie=result['headers']['Set-Cookie'].split(';')[0]
        return result
    def register(self,email='candidate@example.com'):
        r=self.req('/api/register',{'name':'Test Candidate','email':email,'password':'CorrectHorse123!'});self.assertEqual(r['status'],200);return r
    def apply_and_complete(self):
        self.register()
        r=self.req('/api/applications',{'role_id':'growth','experience':'I built a measurable workflow.','consent':True});self.assertEqual(r['status'],200);aid=r['body']['id']
        for i in range(4):
            rr=self.req('/api/applications/'+aid+'/answer',{'answer':'Tracked improvement number %d.'%i,'turn':i});self.assertEqual(rr['status'],200)
        self.assertEqual(self.req('/api/applications/'+aid+'/finish',{})['status'],200)
        return aid
    def pending(self,aid):
        with self.app.store.db() as db:
            row=db.execute('SELECT failures FROM pending_reports WHERE application_id=?',(aid,)).fetchone()
        return row['failures'] if row else None
    def test_transcript_syncs_and_report_retries_independently(self):
        aid=self.apply_and_complete()
        # First pass: report fails (502) but transcript must sync and version must be marked.
        self.app.work_once()
        a=self.app.store.get(aid)
        self.assertEqual(a['sync_status'],'Synced','sync must not be held hostage by a failed report')
        self.assertIsNone(a.get('evaluation'))
        self.assertEqual(self.pending(aid),0,'failed report must leave a pending retry job')
        self.assertEqual(self.cu.records[-1]['status'],'completed')
        # Second pass: pending lane re-runs the report after its short delay.
        with self.app.store.db() as db: db.execute('UPDATE pending_reports SET next_retry=0 WHERE application_id=?',(aid,))
        self.app.work_once()
        a=self.app.store.get(aid)
        self.assertIsNotNone(a.get('evaluation'),'report must recover on retry')
        self.assertEqual(a['evaluation']['summary'],'Recovered report after retry.')
        self.assertIsNone(self.pending(aid),'pending job must be removed after success')
        # Report push reused the same task: total syncs = 2 (transcript, then report).
        self.assertEqual(self.cu.syncs,2)
        self.assertIn('Recovered report after retry.',self.cu.records[-1]['evaluation']['summary'] if self.cu.records[-1].get('evaluation') else '')
    def test_permanent_report_failure_keeps_pending_and_does_not_resync_transcript(self):
        aid=self.apply_and_complete()
        self.ai.remaining=99
        self.app.work_once()  # syncs transcript, queues report
        with self.app.store.db() as db: db.execute('UPDATE pending_reports SET next_retry=0 WHERE application_id=?',(aid,))
        self.app.work_once()  # report fails again
        a=self.app.store.get(aid)
        self.assertEqual(a['sync_status'],'Synced')
        self.assertIsNone(a.get('evaluation'))
        self.assertEqual(self.pending(aid),1,'pending job must back off, not vanish')
        self.assertEqual(len(self.cu.records),1,'no ClickUp call may happen while the report itself keeps failing')
    def test_quota_failure_defers_report_instead_of_blocking(self):
        aid=self.apply_and_complete()
        with patch.dict(os.environ,{'MAX_AI_CALLS_PER_DAY':'0'}):
            self.app.work_once()
        a=self.app.store.get(aid)
        self.assertEqual(a['sync_status'],'Synced','quota exhaustion must defer the report, not block sync')
        self.assertEqual(self.pending(aid),0)
    def test_report_already_present_needs_no_pending_job(self):
        aid=self.apply_and_complete()
        self.ai.remaining=0
        self.app.work_once()
        a=self.app.store.get(aid)
        self.assertEqual(a['sync_status'],'Synced')
        self.assertIsNotNone(a.get('evaluation'))
        self.assertIsNone(self.pending(aid))
        self.assertEqual(self.cu.syncs,1)

if __name__=='__main__':unittest.main()
