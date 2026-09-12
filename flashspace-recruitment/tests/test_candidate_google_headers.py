"""Header policy tests use synthetic responses, not external resources."""
import unittest
from unittest.mock import patch
from backend.candidate_google import WorkspaceApp, ManualWorkspaceApp
from backend import workspace_staging_asgi
class GoogleHeaderTests(unittest.TestCase):
    def test_staging_uses_google_capable_app(self):
        self.assertIs(workspace_staging_asgi.WorkspaceApp,WorkspaceApp)
    def test_google_origins_only_on_enabled_candidate_login(self):
        app=object.__new__(WorkspaceApp)
        original="default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; connect-src 'self'; frame-ancestors 'none'"
        def response(_app,env,start):
            start('200 OK',[('Content-Security-Policy',original)])
            return [b'synthetic login']
        for enabled,path in [(True,'/candidate/login'),(False,'/candidate/login'),(True,'/recruiter/login'),(True,'/interview-v2')]:
            result={}
            with self.subTest(enabled=enabled,path=path),patch.object(ManualWorkspaceApp,'__call__',response),patch.object(WorkspaceApp,'google_enabled',return_value=enabled):
                app({'PATH_INFO':path},lambda status,headers:result.update(dict(headers)))
            if enabled and path=='/candidate/login':
                self.assertIn('https://accounts.google.com/gsi/client',result['Content-Security-Policy'])
                self.assertIn('frame-src https://accounts.google.com/gsi/',result['Content-Security-Policy'])
                self.assertEqual(result['Cross-Origin-Opener-Policy'],'same-origin-allow-popups')
            else:
                self.assertEqual(result['Content-Security-Policy'],original)
                self.assertNotIn('Cross-Origin-Opener-Policy',result)
if __name__=='__main__':unittest.main()
