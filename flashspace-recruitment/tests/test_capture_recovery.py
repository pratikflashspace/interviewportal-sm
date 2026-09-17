import shutil
import subprocess
import unittest
from pathlib import Path
class CaptureRecoveryTests(unittest.TestCase):
    def test_browser_capture_lifecycle_logic(self):
        if not shutil.which('node'):self.skipTest('Node unavailable')
        path=Path(__file__).resolve().parents[1]/'web/src/v2/capture-recovery.test.mjs'
        result=subprocess.run(['node','--test',str(path)],capture_output=True,text=True,timeout=20)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
