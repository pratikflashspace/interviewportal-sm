"""Candidate-only UI scope and executable JavaScript transport tests."""
from pathlib import Path
import shutil
import subprocess
import unittest
ROOT=Path(__file__).resolve().parents[1]/'web/src/auth'
class GoogleClientTests(unittest.TestCase):
    def test_transport(self):
        if not shutil.which('node'):self.skipTest('Node unavailable')
        r=subprocess.run(['node','--test',str(ROOT/'candidate-google-client.test.mjs')],capture_output=True,text=True,timeout=20)
        self.assertEqual(r.returncode,0,r.stdout+r.stderr)
    def test_candidate_only_and_disabled_until_configured(self):
        page=(ROOT/'LoginPage.jsx').read_text();widget=(ROOT/'CandidateGoogleSignIn.jsx').read_text();client=(ROOT/'candidate-google-client.mjs').read_text()
        self.assertIn('!recruiter&&<CandidateGoogleSignIn',page)
        self.assertIn('if(!config.enabled)',widget)
        self.assertLess(widget.index('if(!config.enabled)'),widget.index('await loadGoogleSdk'))
        self.assertIn('auto_select:false',widget);self.assertNotIn('.prompt(',widget)
        self.assertIn('claimed=true',widget);self.assertIn('controller.abort()',widget)
        for bad in ('localStorage','sessionStorage','console.log','tokeninfo'):
            self.assertNotIn(bad,widget+client)
if __name__=='__main__':unittest.main()
