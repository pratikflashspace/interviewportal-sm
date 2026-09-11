import shutil,subprocess,unittest
from pathlib import Path
class WorkletSetupTests(unittest.TestCase):
 def test_bounded_setup(self):
  if not shutil.which('node'):self.skipTest('Node unavailable')
  p=Path(__file__).resolve().parents[1]/'web/src/v2/worklet-setup.test.mjs'
  r=subprocess.run(['node','--test',str(p)],capture_output=True,text=True,timeout=20)
  self.assertEqual(r.returncode,0,r.stdout+r.stderr)
