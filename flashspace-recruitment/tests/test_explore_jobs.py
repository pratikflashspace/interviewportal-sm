"""Explore Jobs scope and executable filtering/transport tests; no live services."""
from pathlib import Path
import shutil
import subprocess
import unittest
ROOT=Path(__file__).resolve().parents[1]
class ExploreJobsTests(unittest.TestCase):
    def test_logic_and_transport(self):
        if not shutil.which('node'):self.skipTest('Node unavailable')
        r=subprocess.run(['node','--test',str(ROOT/'web/src/workspace/explore-jobs.test.mjs')],capture_output=True,text=True,timeout=20)
        self.assertEqual(r.returncode,0,r.stdout+r.stderr)
    def test_only_approved_candidate_route_and_safe_modal_text(self):
        source=(ROOT/'web/src/workspace/ExploreJobs.jsx').read_text()
        main=(ROOT/'web/src/main.jsx').read_text()
        self.assertIn("path==='/candidate/workspace/jobs'?<ExploreJobs/>",main)
        for forbidden in ('dangerouslySetInnerHTML','/admin/','/recruiter/','getUserMedia','MediaRecorder'):
            self.assertNotIn(forbidden,source)
        self.assertIn('candidateIdentity(identity)',source)
        self.assertIn('display(selected.details)',source)
        self.assertIn('submitCareerApplication',source)
        self.assertIn('existingDestination',source)
        self.assertIn('lock.current',source)
        self.assertIn('white-space:pre-wrap',(ROOT/'web/src/workspace/explore-jobs.css').read_text())
if __name__=='__main__':unittest.main()
