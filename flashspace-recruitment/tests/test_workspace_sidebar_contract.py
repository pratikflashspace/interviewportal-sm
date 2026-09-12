"""Source wiring checks complement WSGI tests and browser acceptance."""
from pathlib import Path
import unittest
ROOT=Path(__file__).resolve().parents[1]/'web/src'
class SidebarContract(unittest.TestCase):
    def test_expected_navigation_has_handlers(self):
        code=(ROOT/'workspace/Workspace.jsx').read_text()
        for name in ('My Applications','My Interviews','My Profile','Resume','Settings','Help & Support','Candidates','Analytics','Company'):
            self.assertIn(name,code)
        for name in ('<Settings','<Support','<Resume','<Company','<Analytics','<Candidates','<Pipeline'):
            self.assertIn(name,code)
        self.assertNotIn("['team','Team']",code)
        self.assertNotIn('MFA setup',code)
        self.assertIn("base+'profile'",code)
    def test_public_entry_not_mixed_legacy_app(self):
        code=(ROOT/'main.jsx').read_text()
        self.assertNotIn("import App from",code)
        self.assertIn('<Workspace/>',code)
        code=(ROOT/'workspace/Workspace.jsx').read_text()
        self.assertIn('Login / Sign up',code)
        self.assertIn('if(!path)return <Public/>',code)
    def test_sidebar_writes_use_real_api(self):
        code=(ROOT/'workspace/Features.jsx').read_text()
        for endpoint in ('/workspace/password','/workspace/settings','/workspace/recruiter/company','/workspace/support','/workspace/recruiter/analytics','/workspace/recruiter/candidates'):
            self.assertIn(endpoint,code)
        self.assertIn('No email was sent',code)
        self.assertIn('File uploads are not available',code)
        self.assertNotIn('localStorage',code)

if __name__=='__main__':unittest.main()
