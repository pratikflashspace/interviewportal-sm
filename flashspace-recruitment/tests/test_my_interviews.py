from pathlib import Path
import shutil
import subprocess
import unittest
ROOT=Path(__file__).resolve().parents[1]
class MyInterviewsTests(unittest.TestCase):
    def test_node_logic(self):
        if not shutil.which('node'):self.skipTest('Node unavailable')
        r=subprocess.run(['node','--test',str(ROOT/'web/src/workspace/my-interviews.test.mjs')],capture_output=True,text=True,timeout=20)
        self.assertEqual(r.returncode,0,r.stdout+r.stderr)
    def test_scoped_route_guard_and_no_capture(self):
        s=(ROOT/'web/src/workspace/MyInterviews.jsx').read_text();main=(ROOT/'web/src/main.jsx').read_text()
        self.assertIn("path==='/candidate/workspace/interviews'?<MyInterviews/>",main)
        for forbidden in ('/admin/','/recruiter/','getUserMedia','MediaRecorder','15 minutes','/answer','/speech'):
            self.assertNotIn(forbidden,s)
        self.assertIn('candidateIdentity(identity)',s);self.assertIn('const fresh=applicationsView',s);self.assertIn('interviewAction(item)',s);self.assertIn('actionController.current?.abort()',s)
    def test_detail_link_only_resolves_owned_rows(self):
        s=(ROOT/'web/src/workspace/MyApplications.jsx').read_text()
        self.assertIn('if(result.some(a=>a.id===linked))setSelectedId(linked)',s)
        self.assertIn('This application is not available in your account.',s)
if __name__=='__main__':unittest.main()
