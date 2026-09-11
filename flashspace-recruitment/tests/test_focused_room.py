import shutil,subprocess,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
class FocusedRoomTests(unittest.TestCase):
 def test_approved_layout_and_no_removed_controls(self):
  source=(ROOT/'web/src/v2/IntegratedInterview.jsx').read_text()
  for text in ('Pause interview','Use typing alternative','Reload saved state','Saved questions and answers','10 core questions','setRevealed(null)','setTyping('):self.assertNotIn(text,source)
  for text in ('room-participants','room-question','Begin interview','Check camera and microphone','I heard the test sound','micDetected','cameraConfirmed','disclosure.qid===flow?.active?.id'):self.assertIn(text,source)
  self.assertIn("played.current.set(f.active.id,count)",source)
 def test_question_markup_never_contains_hidden_full_copy(self):
  source=(ROOT/'web/src/v2/spoken-question.jsx').read_text()
  self.assertNotIn('interview-sr',source);self.assertNotIn('aria-hidden',source)
  self.assertIn('visibleWords',source)
 def test_node_reveal(self):
  if not shutil.which('node'):self.skipTest('Node unavailable')
  result=subprocess.run(['node','--test',str(ROOT/'web/src/v2/question-reveal.test.mjs')],capture_output=True,text=True,timeout=20)
  self.assertEqual(result.returncode,0,result.stdout+result.stderr)
if __name__=='__main__':unittest.main()
