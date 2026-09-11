"""Interview-only presentation contracts; no provider or database operations."""
from pathlib import Path
import unittest
ROOT=Path(__file__).resolve().parents[1]/'web/src/v2'
class ScreenScopeTests(unittest.TestCase):
    def test_controls_and_preflight_remain_real(self):
        src=(ROOT/'IntegratedInterview.jsx').read_text()
        for forbidden in ('>Pause interview<','>Use typing alternative<','>Start Recording Answer<','>Reload Saved State<','Saved questions and answers'):
            self.assertNotIn(forbidden,src)
        for expected in ('checkDevices','micDetected','cameraConfirmed','consent','Begin interview','room-preflight','room-question','room-participants'):
            self.assertIn(expected,src)
        self.assertIn('!started&&!done',src)
        self.assertIn('currentTime',src)
        self.assertIn('revealed={shown}',src)
    def test_correct_waveform_classes_and_mobile_constraints(self):
        css=(ROOT/'focused-room.css').read_text()
        self.assertIn('.focused-room .voice-viz-bars',css)
        self.assertIn('minmax(0,1fr) minmax(0,1fr)',css)
        self.assertIn('object-fit:contain',css)
        self.assertIn('@media(max-width:360px)',css)
        self.assertIn('prefers-reduced-motion',css)
        self.assertNotIn('.voice-visualizer',css)
        self.assertNotIn('.tr-shell',css)
        self.assertNotIn('.sidebar',css)
    def test_undisclosed_words_not_rendered_as_hidden_full_text(self):
        src=(ROOT/'spoken-question.jsx').read_text()
        self.assertIn('visibleWords(text,revealed)',src)
        self.assertNotIn('dangerouslySetInnerHTML',src)
        self.assertNotIn('sr-only',src)
        self.assertNotIn('>{text}<',src)

if __name__=='__main__':unittest.main()
