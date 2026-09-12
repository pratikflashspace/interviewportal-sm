import shutil,subprocess,unittest
from pathlib import Path
class DeviceChecks(unittest.TestCase):
 def test_device_checks_before_recording(self):
  if not shutil.which('node'):self.skipTest('Node unavailable')
  file=Path(__file__).resolve().parents[1]/'web/src/v2/device-check.test.mjs'
  result=subprocess.run(['node','--test',str(file)],capture_output=True,text=True,timeout=20)
  self.assertEqual(result.returncode,0,result.stdout+result.stderr)
