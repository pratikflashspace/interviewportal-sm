"""Dashboard contracts, actual Node calculations, and real isolated WSGI reads."""
import json
from pathlib import Path
import shutil
import subprocess
import unittest
import test_workspace_server as fixtures
ROOT=Path(__file__).resolve().parents[1]
class DashboardTests(unittest.TestCase):
    setUp=fixtures.WorkspaceTests.setUp
    req=fixtures.WorkspaceTests.req
    signup=fixtures.WorkspaceTests.signup
    recruiter=fixtures.WorkspaceTests.recruiter
    login_recruiter=fixtures.WorkspaceTests.login_recruiter
    def test_current_candidate_only_reads(self):
        self.assertEqual(self.req('/api/workspace/candidate/applications')['status'],401)
        self.signup();first=self.cookie
        r=self.req('/api/applications',{'role_id':fixtures.ROLE['id'],'experience':'Synthetic dashboard application context','consent':True})
        self.assertEqual(r['status'],200,r)
        aid=r['body']['id']
        own=self.req('/api/workspace/candidate/applications')['body']
        self.assertEqual([a['id'] for a in own],[aid])
        self.assertNotIn('evaluation',own[0]);self.assertNotIn('user_id',own[0])
        self.signup('other-dashboard@example.com');self.assertEqual(self.req('/api/workspace/candidate/applications')['body'],[])
        self.assertEqual(len(self.req('/api/workspace/candidate/applications',cookie=first)['body']),1)
        self.recruiter();self.login_recruiter()
        for route in ('applications','recommendations'):
            self.assertEqual(self.req('/api/workspace/candidate/'+route)['status'],403)
    def test_recommendations_require_applied_role_not_profile(self):
        self.signup()
        p=self.req('/api/workspace/profile')['body']
        self.req('/api/workspace/profile',{'version':p['version'],'fields':{'skills':', '.join(fixtures.ROLE['skills'])}})
        self.assertEqual(self.req('/api/workspace/candidate/recommendations')['body'],[])
        role=fixtures.ROLE
        for identifier,published,department,skills in [('similar',True,role['department'],['Unrelated']),('draft-match',False,role['department'],role['skills']),('different',True,'Unrelated',['Unrelated'])]:
            data={**role,'id':identifier,'title':identifier,'department':department,'skills':skills}
            with self.app.store.db() as db:
                db.execute('INSERT INTO managed_roles VALUES (?,?,?,?,?,?,?)',(identifier,json.dumps(data),'published' if published else 'draft',1,'synthetic','synthetic','test'))
        self.req('/api/applications',{'role_id':role['id'],'experience':'Synthetic dashboard application context','consent':True})
        found=self.req('/api/workspace/candidate/recommendations')['body']
        self.assertEqual([item['role']['id'] for item in found],['similar'])
    def test_node_dashboard_logic(self):
        if not shutil.which('node'):self.skipTest('Node unavailable')
        r=subprocess.run(['node','--test',str(ROOT/'web/src/workspace/candidate-dashboard.test.mjs')],capture_output=True,text=True,timeout=20)
        self.assertEqual(r.returncode,0,r.stdout+r.stderr)
    def test_page_scoped_routing_and_no_recruiter_links(self):
        source=(ROOT/'web/src/workspace/CandidateDashboard.jsx').read_text()
        main=(ROOT/'web/src/main.jsx').read_text()
        self.assertIn("path==='/candidate/workspace/dashboard'?<CandidateDashboard/>",main)
        self.assertIn("path==='/interview-v2'?<IntegratedInterview/>",main)
        self.assertNotIn('/recruiter/',source);self.assertNotIn('/admin/',source)
        self.assertIn('candidateIdentity(identity)',source)
        self.assertIn('Resume links are supported. File upload is not available yet.',source)
        self.assertIn('Completed / total interviews',source)
        self.assertIn('if(alive)setData(value)',source)
        self.assertIn('controller.abort()',source)
if __name__=='__main__':unittest.main()
