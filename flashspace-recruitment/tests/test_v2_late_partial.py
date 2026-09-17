import shutil
import subprocess
import unittest
from pathlib import Path

class LatePartialTests(unittest.TestCase):
    def test_partial_after_end_waits_for_final_without_phantom_speech(self):
        if not shutil.which('node'):self.skipTest('Node unavailable')
        uri=(Path(__file__).resolve().parents[1]/'web/src/v2/turn-controller.mjs').as_uri()
        script=f'''import assert from 'node:assert/strict';
import {{TurnController}} from {uri!r};
let now=0;const c=new TurnController(()=>now);c.begin();c.playbackEnded(c.epoch);
c.speechStart(0);c.speechEnd();now=1000;c.partial(0);
assert.equal(c.speaking,false);assert.equal(c.ready(),false);
c.final(0,'Complete response');now=6999;assert.equal(c.ready(),false);
now=7000;assert.equal(c.ready(),true);
'''
        result=subprocess.run(['node','--input-type=module','-e',script],capture_output=True,text=True,timeout=15)
        self.assertEqual(result.returncode,0,result.stderr)
