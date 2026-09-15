from pathlib import Path
import shutil,subprocess,unittest
ROOT=Path(__file__).resolve().parents[1]
class ProfileUITests(unittest.TestCase):
 def test_node_transport(self):
  if not shutil.which('node'):self.skipTest('Node unavailable')
  r=subprocess.run(['node','--test',str(ROOT/'web/src/workspace/candidate-profile.test.mjs')],capture_output=True,text=True,timeout=20);self.assertEqual(r.returncode,0,r.stdout+r.stderr)
 def test_scope_and_draft_guards(self):
  s=(ROOT/'web/src/workspace/CandidateProfile.jsx').read_text();main=(ROOT/'web/src/main.jsx').read_text()
  self.assertIn("path==='/candidate/workspace/profile'?<CandidateProfile/>",main)
  for forbidden in ('/recruiter/','dangerouslySetInnerHTML','localStorage','sessionStorage','type="file"'):self.assertNotIn(forbidden,s)
  for required in ('readOnly value={profile.email}','beforeunload','Use latest saved section','setConflict(true)','candidateIdentity(user)'):self.assertIn(required,s)
if __name__=='__main__':unittest.main()
