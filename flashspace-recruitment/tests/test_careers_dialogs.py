"""Source-contract tests for the narrow careers UI restoration.

These complement the frontend build and browser review; not live-media E2E.
"""
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]/'web/src'

class CareersDialogContracts(unittest.TestCase):
    def setUp(self):
        self.app=(ROOT/'App.jsx').read_text()
        self.dialog=(ROOT/'CareersDialogs.jsx').read_text()

    def test_plain_role_overlay_removed(self):
        self.assertNotIn('aria-label="Role details" className="role-editor"',self.app)
        self.assertIn('<CareersDialogs',self.app)
        self.assertIn('<DialogContent><DialogTitle>{selected?.title}',self.dialog)
        for text in ('What you’ll work on','className="skills"','className="soft-note"'):
            self.assertIn(text,self.dialog)

    def test_apply_opens_original_profile_modal_not_standalone_form(self):
        start=self.app.split('async function startRole(role){',1)[1].split('\n',1)[0]
        self.assertIn('openApplication(existing)',start)
        self.assertIn('setApplyRole(role)',start)
        self.assertNotIn('window.location.assign',start)
        self.assertIn('First, a little about you.',self.dialog)
        self.assertIn('Resume or portfolio link (optional)',self.dialog)
        self.assertIn('applyRole:LIVE?null:applyRole',self.app)

    def test_submission_keeps_v2_and_explicit_consent(self):
        self.assertIn("request('/api/v2/applications'",self.dialog)
        self.assertIn("consent_version:'flashspace-sarvam-conversation-v2'",self.dialog)
        self.assertIn("form.get('consent')",self.dialog)
        self.assertIn("portfolio:form.get('portfolio')",self.dialog)
        self.assertIn("credentials:'same-origin'",self.dialog)
        self.assertIn("'X-Requested-With':'Flashspace'",self.dialog)
        self.assertIn('submitCareerApplication(applyRole,form)',self.app)
        self.assertIn("encodeURIComponent(aid)",self.app)
        self.assertIn('separate consent inside the interview',self.dialog)
        self.assertNotIn('Cloudflare',self.dialog)

    def test_existing_branding_and_v2_resume_preserved(self):
        self.assertIn('teamrecrut',self.app)
        self.assertIn('function Brandmark()',self.app)
        self.assertIn('a.flow_version===2',self.app)
        self.assertIn("'/interview-review?application='",self.app)
        self.assertIn('await startRole(role)',self.app)

if __name__=='__main__':unittest.main()
