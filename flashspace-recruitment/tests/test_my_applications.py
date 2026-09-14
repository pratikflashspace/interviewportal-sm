"""Candidate page scope and persisted WSGI history, without external services."""
from pathlib import Path
import shutil
import subprocess
import unittest
import test_workspace_server as fixtures
ROOT=Path(__file__).resolve().parents[1]
class MyApplicationsTests(unittest.TestCase):
    setUp=fixtures.WorkspaceTests.setUp
    req=fixtures.WorkspaceTests.req
    signup=fixtures.WorkspaceTests.signup
    recruiter=fixtures.WorkspaceTests.recruiter
    login_recruiter=fixtures.WorkspaceTests.login_recruiter
    def test_own_persisted_history_and_recruiter_denial(self):
        path='/api/workspace/candidate/applications'
        self.assertEqual(self.req(path)['status'],401)
        self.signup();first=self.cookie
        r=self.req('/api/applications',{'role_id':fixtures.ROLE['id'],'experience':'Synthetic application tracking context','consent':True});self.assertEqual(r['status'],200,r);aid=r['body']['id']
        a=self.app.store.get(aid);a['status']='completed';self.app.store.save(a)
        queued=self.req(path)['body'][0];self.assertEqual(queued['version'],0);self.assertEqual(queued['events'],[])
        self.recruiter();self.login_recruiter();self.assertEqual(self.req(path)['status'],403)
        r=self.req('/api/workspace/recruiter/applications/'+aid+'/stage',{'version':0,'stage':'shortlisted'});self.assertEqual(r['status'],200,r)
        own=self.req(path,cookie=first)['body'];self.assertEqual(len(own),1);self.assertEqual(own[0]['stage'],'shortlisted');self.assertEqual(own[0]['interview_status'],'completed');self.assertEqual(own[0]['events'][0]['stage'],'shortlisted');self.assertTrue(own[0]['events'][0]['created'])
        for key in ('evaluation','score','notes','actor','model_confidence'):self.assertNotIn(key,own[0]);self.assertNotIn(key,own[0]['events'][0])
        self.signup('other-application@example.com');self.assertEqual(self.req(path)['body'],[])
        self.assertEqual(self.req(path,cookie=first)['body'][0]['id'],aid)
    def test_node_logic(self):
        if not shutil.which('node'):self.skipTest('Node unavailable')
        r=subprocess.run(['node','--test',str(ROOT/'web/src/workspace/my-applications.test.mjs')],capture_output=True,text=True,timeout=20)
        self.assertEqual(r.returncode,0,r.stdout+r.stderr)
    def test_page_is_candidate_only_and_no_interview_mutations(self):
        s=(ROOT/'web/src/workspace/MyApplications.jsx').read_text();main=(ROOT/'web/src/main.jsx').read_text()
        self.assertIn("path==='/candidate/workspace/applications'?<MyApplications/>",main)
        for forbidden in ('/recruiter/','/admin/','MediaRecorder','getUserMedia','dangerouslySetInnerHTML'):self.assertNotIn(forbidden,s)
        self.assertIn('candidateIdentity(user)',s);self.assertIn('continuation(a)',s)
        self.assertIn('const fresh=applicationsView',s);self.assertIn('lock.current',s)
if __name__=='__main__':unittest.main()
