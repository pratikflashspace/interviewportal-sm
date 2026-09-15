"""Interview-only presentation contracts; no provider or database operations."""
from pathlib import Path
import unittest
ROOT=Path(__file__).resolve().parents[1]/'web/src/v2'
class ScreenScopeTests(unittest.TestCase):
    def test_controls_and_preflight_remain_real(self):
        src=(ROOT/'IntegratedInterview.jsx').read_text()
        for forbidden in ('>Pause interview<','>Use typing alternative<','>Start Recording Answer<','>Reload Saved State<','Saved questions and answers','Hear again','getUserMedia({video','<video','Play test sound'):
            self.assertNotIn(forbidden,src)
        for expected in ('checkDevices','micDetected','consent','Begin interview','room-preflight','room-question','room-participants','Check your microphone'):
            self.assertIn(expected,src)
        self.assertIn('!started&&!done',src)
        self.assertIn('currentTime',src)
        self.assertIn('revealed={shown}',src)
    def test_correct_waveform_classes_and_mobile_constraints(self):
        css=(ROOT/'focused-room.css').read_text()
        self.assertIn('.focused-room .voice-viz-bars',css)
        self.assertIn('minmax(0,1fr) minmax(0,1fr)',css)
        self.assertIn('.focused-room .room-candidate .voice-viz',css)
        self.assertIn('@media(max-width:360px)',css)
        self.assertIn('prefers-reduced-motion',css)
        self.assertNotIn('.voice-visualizer',css)
        self.assertNotIn('.tr-shell',css)
        self.assertNotIn('.sidebar',css)
        self.assertNotIn('video',css)
    def test_undisclosed_words_not_rendered_as_hidden_full_text(self):
        src=(ROOT/'spoken-question.jsx').read_text()
        self.assertIn('visibleWords(text,revealed)',src)
        self.assertNotIn('dangerouslySetInnerHTML',src)
        self.assertNotIn('sr-only',src)
        self.assertNotIn('>{text}<',src)

if __name__=='__main__':unittest.main()


class TapToSpeakContract(unittest.TestCase):
    """Button-driven turns: mic opens only on Tap to speak and closes at Done."""

    def test_room_has_tap_and_done_controls(self):
        src = (ROOT / 'IntegratedInterview.jsx').read_text()
        for expected in ('Tap to speak', 'I\u2019m done speaking', 'tapToSpeak', 'doneSpeaking',
                          "status==='awaiting-tap'", "status==='listening'", 'awaiting-tap'):
            self.assertIn(expected, src)
        # The mic must never be open while the interviewer speaks.
        self.assertNotIn("stopAudio();\n    if(msg.event==='transcript.partial')", src)

    def test_interviewer_speech_is_never_interrupted_by_noise(self):
        src = (ROOT / 'IntegratedInterview.jsx').read_text()
        # Old bug: openSpeech() ran before the question played, so background noise
        # during playback called stopAudio() and cut the question mid-sentence.
        self.assertNotIn('connectSpeech();const p=await allowance', src)
        self.assertIn('await connectSpeech();if(paused.current||run!==epoch.current)return;setStatus(', src)

    def test_css_has_button_styles(self):
        css = (ROOT / 'focused-room.css').read_text()
        self.assertIn('.focused-room .room-tap', css)
        self.assertIn('.focused-room .room-done', css)
