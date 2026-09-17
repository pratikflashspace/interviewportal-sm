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

    def test_turn_controller_re_arms_for_every_question(self):
        src = (ROOT / 'IntegratedInterview.jsx').read_text()
        # Regression (staging): Q1 worked, Q2+ froze because advance() left the
        # TurnController paused, so every speech event from Q2 onward was rejected.
        self.assertIn('await restore(next);ctl.current.begin();', src)

    def test_done_tap_waits_for_late_final_transcript(self):
        src = (ROOT / 'IntegratedInterview.jsx').read_text()
        # Regression (staging, first question only): the coldest upstream STT
        # connection emits the final transcript a moment after the candidate stops
        # speaking, so a fast done-tap read an empty transcript, showed an error,
        # and required a manual re-tap. doneSpeaking must now wait a grace window
        # for the late final instead of erroring immediately.
        self.assertIn('Still transcribing your last words', src)
        self.assertIn('deadline', src)
        # The mic socket must stay open during the grace window.
        self.assertIn('const live=!!speech.current;', src)
        # The old immediate-error path must be gone.
        self.assertNotIn("if(!answer){setError('No speech was captured yet. Answer out loud, then tap", src)

    def test_completion_redirects_to_my_applications(self):
        src = (ROOT / 'IntegratedInterview.jsx').read_text()
        # After the last answer, the room must not strand the candidate: it shows a
        # completion panel and auto-redirects to My Applications (where the status is
        # visible) with an immediate link for the impatient.
        self.assertIn('Interview complete', src)
        self.assertIn("location.assign('/candidate/workspace/applications')", src)
        self.assertIn('setTimeout', src)

    def test_speech_fetch_retries_once_before_silent_fallback(self):
        src = (ROOT / 'IntegratedInterview.jsx').read_text()
        # Regression (staging): domain questions lost voice for a stretch when a
        # transient Sarvam blip failed the single speech fetch; the room immediately
        # fell back to silent text. One retry now runs before the fallback.
        self.assertIn('const fetchSpeech=', src)
        self.assertIn("setTimeout(r,1200)", src)
        self.assertIn('blob=await fetchSpeech();', src)

    def test_provider_failures_are_recoverable_not_fatal(self):
        src = (ROOT / 'IntegratedInterview.jsx').read_text()
        # Regression (staging): a transient Sarvam TTS/socket hiccup mid-interview
        # hit stopWithError() and ended the attempt with the technical-stop panel.
        # Now TTS failure reveals the question text and a socket drop keeps the
        # transcript with reconnect-or-done; only usage limits and failed submits stop.
        self.assertIn('voiceLost(', src)
        self.assertIn("revealFull();setWarn('Question audio is unavailable", src)
        self.assertIn("status==='voice-lost'", src)
        # The still-fatal paths must remain fatal.
        self.assertIn("usage_limit_reached", src)
        self.assertIn('Contact support before retrying an uncertain submission', src)

    def test_css_has_button_styles(self):
        css = (ROOT / 'focused-room.css').read_text()
        self.assertIn('.focused-room .room-tap', css)
        self.assertIn('.focused-room .room-done', css)
