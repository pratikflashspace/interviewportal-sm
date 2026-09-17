import unittest
from backend.v2_speech_events import SpeechEvents

class SpeechEventsTests(unittest.TestCase):
    def event(self,kind,index):return {'event':kind,'utterance_idx':index}
    def test_old_end_not_forwarded_over_current_speech(self):
        guard=SpeechEvents()
        guard.accept(self.event('vad.speech_start',0));guard.accept(self.event('vad.speech_start',1))
        self.assertIsNone(guard.accept(self.event('vad.speech_end',0)))
        final=self.event('transcript.final',0)
        self.assertEqual(guard.accept(final),final)
        end=self.event('vad.speech_end',1)
        self.assertEqual(guard.accept(end),end)
    def test_final_is_not_acoustic_end(self):
        guard=SpeechEvents();guard.accept(self.event('vad.speech_start',0));guard.accept(self.event('transcript.final',0))
        self.assertEqual(guard.speaking,{0})
    def test_duplicates_and_event_budget(self):
        guard=SpeechEvents();guard.accept(self.event('transcript.final',0))
        self.assertIsNone(guard.accept(self.event('transcript.partial',0)))
        self.assertIsNone(guard.accept(self.event('vad.speech_start',0)))
        with self.assertRaises(ValueError):guard.accept(self.event('vad.speech_start',10001))
