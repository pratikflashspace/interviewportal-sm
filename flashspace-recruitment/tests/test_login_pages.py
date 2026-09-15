"""Approved login-page route contracts plus actual JS transport tests."""
from pathlib import Path
import shutil
import subprocess
import unittest
ROOT=Path(__file__).resolve().parents[1]/'web/src'
class LoginPageTests(unittest.TestCase):
    def test_manual_login_transport(self):
        if not shutil.which('node'):self.skipTest('Node is unavailable')
        result=subprocess.run(['node','--test',str(ROOT/'auth/login-client.test.mjs')],capture_output=True,text=True,timeout=20)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
    def test_only_login_routes_intercepted(self):
        source=(ROOT/'main.jsx').read_text()
        self.assertIn("path==='/candidate/login'",source)
        self.assertIn("path==='/recruiter/login'",source)
        self.assertNotIn("path==='/candidate/signup'",source)
        self.assertIn('<Workspace/>',source)
        self.assertIn('<IntegratedInterview/>',source)
    def test_no_unconfigured_google_recovery_or_recruiter_signup(self):
        source=(ROOT/'auth/LoginPage.jsx').read_text()
        self.assertNotIn('/recruiter/signup',source)
        self.assertNotIn('/google',source)
        self.assertNotIn('Forgot password',source)
        self.assertNotIn('<aside',source)
        self.assertIn('recruiter?<p',source)
        self.assertIn('/candidate/signup',source)
        self.assertIn('submitting.current',source)
        self.assertIn('controller.current?.abort()',source)
        self.assertIn('aria-invalid',source)
        self.assertNotIn('localStorage',source)
        self.assertNotIn('sessionStorage',source)
if __name__=='__main__':unittest.main()
