"""Hybrid provider tests: LLM layer to the Workers AI proxy, voice stays on Sarvam.

No live calls: proxy transport is mocked, Sarvam transport is mocked. The pure
Sarvam AI must remain the default when PRATIK_WORKERS_AI_TOKEN is not set.
"""
import os
import unittest
from unittest.mock import patch

from backend.hybrid_provider import HybridSarvamProvider, hybrid_ai_or_evidence_only
from backend.server import APIError
from backend.workers_proxy import WorkersProxyProvider


class HybridSelectionTests(unittest.TestCase):
    ENV_BASE = {'SARVAM_API_KEY': 'x' * 32, 'APP_ORIGIN': 'http://localhost:8000'}
    PROXY_URL = 'https://pool-a-pratik-ai.yasasv.workers.dev/v1/run'

    def test_pure_sarvam_when_no_proxy_token(self):
        env = {**self.ENV_BASE, 'PRATIK_WORKERS_AI_TOKEN': '', 'PRATIK_WORKERS_AI_URL': self.PROXY_URL}
        with patch.dict(os.environ, env):
            ai = hybrid_ai_or_evidence_only()
        self.assertEqual(type(ai).__name__, 'EvidenceOnlyAI')
        self.assertNotIsInstance(ai.provider, HybridSarvamProvider)

    def test_hybrid_selected_when_proxy_configured(self):
        env = {**self.ENV_BASE, 'PRATIK_WORKERS_AI_TOKEN': 'rotated-token-value',
               'PRATIK_WORKERS_AI_URL': self.PROXY_URL}
        with patch.dict(os.environ, env):
            ai = hybrid_ai_or_evidence_only()
        self.assertEqual(type(ai).__name__, 'HybridEvidenceAI')
        self.assertIsInstance(ai.provider, HybridSarvamProvider)

    def test_wrong_proxy_url_never_activates_hybrid(self):
        env = {**self.ENV_BASE, 'PRATIK_WORKERS_AI_TOKEN': 'rotated-token-value',
               'PRATIK_WORKERS_AI_URL': 'https://evil.example/v1/run'}
        with patch.dict(os.environ, env):
            ai = hybrid_ai_or_evidence_only()
        self.assertEqual(type(ai).__name__, 'EvidenceOnlyAI')


class HybridRoutingTests(unittest.TestCase):
    PROXY_URL = 'https://pool-a-pratik-ai.yasasv.workers.dev/v1/run'

    def _hybrid(self):
        env = {'SARVAM_API_KEY': 'x' * 32, 'PRATIK_WORKERS_AI_TOKEN': 'rotated-token-value',
               'PRATIK_WORKERS_AI_URL': self.PROXY_URL, 'APP_ORIGIN': 'http://localhost:8000'}
        with patch.dict(os.environ, env):
            ai = hybrid_ai_or_evidence_only()
        # Reset the proxy transport to a controlled fake for each test.
        return ai

    def test_structured_goes_to_proxy_llm(self):
        ai = self._hybrid()
        calls = []

        def proxy_structured(self, system, payload, name, schema):
            calls.append(name)
            return {'decision': 'complete'}

        with patch.object(WorkersProxyProvider, 'structured', proxy_structured):
            result = ai.provider.structured('sys', {}, 'turn_completion', {})
        self.assertEqual(result, {'decision': 'complete'})
        self.assertEqual(calls, ['turn_completion'])

    def test_speech_stays_on_sarvam_transport(self):
        ai = self._hybrid()
        paths = []

        def sarvam_send(self, path, body, content_type='application/json'):
            paths.append(path)
            if path.endswith('/text-to-speech'):
                return {'audios': [__import__('base64').b64encode(b'ID3fake-audio').decode()]}
            raise AssertionError('unexpected Sarvam path ' + path)

        def proxy_fail(self, model, payload, audio=False):
            raise AssertionError('speech must not reach the Workers proxy')

        with patch.object(type(ai.provider), '_send', sarvam_send), \
             patch.object(WorkersProxyProvider, 'run', proxy_fail):
            audio = ai.provider.speech('Why this role?')
        self.assertTrue(audio)
        self.assertEqual(paths, ['/text-to-speech'])

    def test_followup_choice_uses_proxy(self):
        ai = self._hybrid()
        seen = {}

        def proxy_structured(self, system, payload, name, schema):
            seen['name'] = name
            seen['payload'] = payload
            return {'choice': 0, 'gap': 'personal contribution'}

        with patch.object(WorkersProxyProvider, 'structured', proxy_structured):
            decision = ai.followup({'text': 'Q', 'followups': ['A?', 'B?']}, 'I led the project.')
        self.assertEqual(decision, {'text': 'A?', 'menu_choice': 0})
        self.assertEqual(seen['name'], 'followup_choice')

    def test_live_followup_generation_grounded_in_role(self):
        ai = self._hybrid()
        seen = {}

        def proxy_structured(self, system, payload, name, schema):
            seen['name'] = name
            seen['payload'] = payload
            return {'question': 'Which two features did you personally ship in that product, and how did you measure adoption?',
                    'gap': 'no shipped outcomes', 'menu_choice': -1}

        role = {'title': 'Product Engineer', 'details': 'Own features end to end.', 'skills': ['React']}
        with patch.object(WorkersProxyProvider, 'structured', proxy_structured):
            decision = ai.followup({'text': 'Tell me about the product.', 'followups': ['A?', 'B?']},
                                   'I built a product with a team.', role)
        self.assertEqual(decision['text'], 'Which two features did you personally ship in that product, and how did you measure adoption?')
        self.assertEqual(seen['name'], 'live_followup')
        self.assertEqual(seen['payload']['role']['title'], 'Product Engineer')
        self.assertIn('style_examples', seen['payload'])

    def test_live_followup_invalid_output_falls_back_to_menu(self):
        ai = self._hybrid()

        def proxy_structured(self, system, payload, name, schema):
            if name == 'live_followup':
                return {'question': 'too short', 'gap': '', 'menu_choice': 1}
            return {'choice': 1, 'gap': ''}

        with patch.object(WorkersProxyProvider, 'structured', proxy_structured):
            decision = ai.followup({'text': 'Q', 'followups': ['A?', 'B?']}, 'I led the project.',
                                    {'title': 'R', 'details': 'd', 'skills': []})
        self.assertEqual(decision, {'text': 'B?', 'menu_choice': 1})

    def test_live_followup_sufficient_evidence_skips_followup(self):
        ai = self._hybrid()

        def proxy_structured(self, system, payload, name, schema):
            if name == 'live_followup':
                return {'question': '', 'gap': 'answer is complete', 'menu_choice': -1}
            raise AssertionError(name)

        with patch.object(WorkersProxyProvider, 'structured', proxy_structured):
            decision = ai.followup({'text': 'Q', 'followups': ['A?', 'B?']}, 'Full answer.',
                                    {'title': 'R', 'details': 'd', 'skills': []})
        self.assertIsNone(decision)


if __name__ == '__main__':
    unittest.main()
