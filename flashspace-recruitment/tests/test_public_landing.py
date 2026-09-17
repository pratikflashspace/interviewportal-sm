from pathlib import Path
import shutil,subprocess,unittest
ROOT=Path(__file__).resolve().parents[1]
class LandingTests(unittest.TestCase):
 def test_transport(self):
  if not shutil.which('node'):self.skipTest('Node unavailable')
  r=subprocess.run(['node','--test',str(ROOT/'web/src/auth/landing-client.test.mjs')],capture_output=True,text=True,timeout=30)
  self.assertEqual(r.returncode,0,r.stdout+r.stderr)
 def test_scoped_entry_and_auth(self):
  s=(ROOT/'web/src/auth/PublicLanding.jsx').read_text();main=(ROOT/'web/src/main.jsx').read_text()
  self.assertIn("path===''?<PublicLanding/>",main)
  for forbidden in ['/auth/recruiter/signup','/auth/recruiter/google','localStorage','sessionStorage','dangerouslySetInnerHTML','getUserMedia']:self.assertNotIn(forbidden,s)
  self.assertIn('workspaceFor(current)',s);self.assertIn('loginManually(role,values',s);self.assertIn('Go to dashboard',s)
  self.assertIn('Password recovery email setup is pending',s)
