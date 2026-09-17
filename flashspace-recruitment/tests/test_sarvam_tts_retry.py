"""TTS retry contract: one retry on transient Sarvam failures, never on quota/auth.

Regression (staging): a single transient Sarvam TTS hiccup at Q5 left the
candidate without question audio mid-interview. The room now degrades
gracefully, and the provider retries transient transport/inference failures
once. Quota/credit/auth failures (401/402/429) are deterministic and must
not be re-attempted (double charge / wasted quota).
"""
import base64
import unittest

from backend.sarvam_provider import SarvamProvider


class Err(Exception):
    def __init__(self, status, message=''):
        self.status = status
        super().__init__(message or str(status))


class FakeProvider(SarvamProvider):
    """Dependency-injected _send; no network is contacted."""

    def __init__(self, outcomes):
        self.calls = 0
        self.outcomes = outcomes
        self.error_type = Err

    def _send(self, path, payload):
        self.calls += 1
        out = self.outcomes[self.calls - 1] if self.calls <= len(self.outcomes) else Err(503)
        if isinstance(out, Exception):
            # Mirror production _send: attach the upstream status for the retry policy.
            out.sarvam_status = getattr(out, 'sarvam_status', out.status)
            raise out
        return out


MP3 = {'audios': [base64.b64encode(b'ID3' + b'x' * 50).decode()]}
QUESTION = 'Tell me about a project you led end to end.'


class TTSRetryTests(unittest.TestCase):
    def test_transient_failure_retries_once_and_succeeds(self):
        p = FakeProvider([Err(502), MP3])
        audio = p.speech(QUESTION)
        self.assertEqual(audio[:3], b'ID3')
        self.assertEqual(p.calls, 2)

    def test_quota_failure_never_retries(self):
        for status in (401, 402, 429):
            p = FakeProvider([Err(status)])
            with self.assertRaises(Err):
                p.speech(QUESTION)
            self.assertEqual(p.calls, 1, 'status %s must not retry' % status)

    def test_double_transient_failure_raises_after_two_calls(self):
        p = FakeProvider([Err(502), Err(502)])
        with self.assertRaises(Err):
            p.speech(QUESTION)
        self.assertEqual(p.calls, 2)

    def test_invalid_audio_payload_does_not_retry(self):
        p = FakeProvider([{'audios': ['not-base64!!']}])
        with self.assertRaises(Err) as caught:
            p.speech(QUESTION)
        self.assertEqual(caught.exception.status, 502)
        self.assertEqual(p.calls, 1)


if __name__ == '__main__':
    unittest.main()
