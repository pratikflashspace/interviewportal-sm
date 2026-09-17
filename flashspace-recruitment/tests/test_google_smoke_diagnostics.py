"""Focused subprocess diagnostics for restricted CI log readers; synthetic only."""
import os
from pathlib import Path
import subprocess
import sys
import unittest

class GoogleSmokeDiagnostics(unittest.TestCase):
    def test_focused_google_suite(self):
        root=Path(__file__).resolve().parents[1]
        env={**os.environ,'PYTHONPATH':str(root)+os.pathsep+str(root/'tests')}
        result=subprocess.run([sys.executable,'-m','unittest','test_candidate_google','test_candidate_google_client','test_candidate_google_headers','-v'],cwd=root/'tests',env=env,capture_output=True,text=True,timeout=90)
        if result.returncode:
            diagnostic=(result.stdout+'\n'+result.stderr)[-6000:]
            for key,value in os.environ.items():
                if any(word in key.upper() for word in ('TOKEN','SECRET','PASSWORD','DATABASE_URL','API_KEY')) and len(value)>3:diagnostic=diagnostic.replace(value,'[REDACTED]')
            if os.getenv('GITHUB_ACTIONS')=='true':
                print('::error title=Candidate Google tests::'+diagnostic.replace('%','%25').replace('\r','%0D').replace('\n','%0A'),flush=True)
        self.assertEqual(result.returncode,0,'Focused Google tests failed; see sanitized diagnostic annotation.')
if __name__=='__main__':unittest.main()
