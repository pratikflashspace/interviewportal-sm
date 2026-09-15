"""Mocked proxy contract/security tests; no live credentials or inference."""
import base64
import io
import json
import os
import unittest
from unittest.mock import patch
from urllib.error import HTTPError, URLError
from urllib.request import Request

from backend.server import APIError
from backend.proxy_server import ProxyAI, create_app
from backend.workers_proxy import WorkersProxyProvider, NoRedirect, ENDPOINT, LLM_MODEL, STT_MODEL, TTS_MODEL, MAX_AUDIO, MAX_RESPONSE


class Response:
    def __init__(self, value, mime='application/json'):
        self.raw = value if isinstance(value, bytes) else json.dumps(value).encode()
        self.headers = {'Content-Type': mime}
    def read(self, limit): return self.raw[:limit]
    def __enter__(self): return self
    def __exit__(self, *args): pass


class ProxyTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {'PRATIK_WORKERS_AI_TOKEN': 'synthetic-test-token', 'PRATIK_WORKERS_AI_URL': ENDPOINT})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.p = WorkersProxyProvider(APIError)

    def respond(self, value, mime='application/json'):
        return patch.object(self.p.opener, 'open', return_value=Response(value, mime))

    def test_fixed_endpoint_and_model_guard(self):
        for url in ('http://pool-a-pratik-ai.yasasv.workers.dev/v1/run', ENDPOINT + '?x=1', 'https://evil.example/v1/run'):
            with patch.dict(os.environ, {'PRATIK_WORKERS_AI_URL': url}):
                with self.assertRaises(APIError): WorkersProxyProvider(APIError)
        with patch.object(self.p.opener, 'open') as send:
            with self.assertRaises(APIError): self.p.run('@cf/other/model', {})
            send.assert_not_called()

    def test_missing_or_header_injection_token_fails_closed(self):
        for token in ('', 'a\nb', 'Bearer abc'):
            with patch.dict(os.environ, {'PRATIK_WORKERS_AI_TOKEN': token}):
                with self.assertRaises(APIError): WorkersProxyProvider(APIError)

    def test_stt_wire_contract(self):
        data = bytes(range(100))
        with self.respond({'success': True, 'result': {'text': ' A useful response. '}}) as send:
            self.assertEqual(self.p.transcribe(data, 'audio/webm;codecs=opus'), {'text': 'A useful response.'})
        req = send.call_args.args[0]
        self.assertEqual(req.full_url, ENDPOINT)
        self.assertEqual(json.loads(req.data), {'model': STT_MODEL, 'input': {'audio': list(data), 'task': 'transcribe'}})
        self.assertEqual(req.get_header('Authorization'), 'Bearer synthetic-test-token')
        self.assertEqual(send.call_args.kwargs['timeout'], 25)
        self.assertNotIn('employee', json.loads(req.data))

    def test_stt_limits_before_network(self):
        with patch.object(self.p.opener, 'open') as send:
            for data, mime in ((b'x'*99, 'audio/webm'), (b'x'*(MAX_AUDIO+1), 'audio/webm'), (b'x'*100, 'text/plain')):
                with self.assertRaises(APIError): self.p.transcribe(data, mime)
            send.assert_not_called()

    def test_empty_transcript_rejected(self):
        with self.respond({'text': ' '}):
            with self.assertRaises(APIError): self.p.transcribe(b'x'*100, 'audio/wav')

    def test_melotts_binary_and_payload(self):
        with self.respond(b'ID3mock-audio', 'audio/mpeg') as send:
            self.assertEqual(self.p.speech('Tell me about your work.'), b'ID3mock-audio')
        self.assertEqual(json.loads(send.call_args.args[0].data), {'model': TTS_MODEL, 'input': {'prompt': 'Tell me about your work.', 'lang': 'en'}})

    def test_base64_audio_envelope(self):
        with self.respond({'result': {'audio': base64.b64encode(b'ID3mock').decode()}}):
            self.assertEqual(self.p.speech('Test question'), b'ID3mock')

    def test_invalid_audio_rejected(self):
        for response, mime in ((b'<html>error</html>', 'audio/mpeg'), ({'audio': 'not-base64!'}, 'application/json'), ({'audio': base64.b64encode(b'not-mp3').decode()}, 'application/json')):
            with self.respond(response, mime):
                with self.assertRaises(APIError): self.p.speech('Test question')

    def test_errors_are_sanitized_and_not_retried(self):
        for code in (301, 302, 307, 308, 401, 403, 500):
            exc = HTTPError(ENDPOINT, code, 'synthetic-test-token private content', {}, io.BytesIO(b'private body'))
            with patch.object(self.p.opener, 'open', side_effect=exc) as send:
                with self.assertRaises(APIError) as caught: self.p.speech('Test question')
            self.assertEqual(send.call_count, 1)
            self.assertNotIn('synthetic-test-token', caught.exception.message)
            self.assertNotIn('private', caught.exception.message)

    def test_redirects_are_blocked(self):
        handler = NoRedirect()
        self.assertIsNone(handler.redirect_request(Request(ENDPOINT), None, 302, '', {}, 'https://evil.example'))

    def test_capacity_retry_is_bounded(self):
        for code in (429, 503):
            failures = [HTTPError(ENDPOINT, code, 'busy', {}, None) for _ in range(2)]
            with patch.object(self.p.opener, 'open', side_effect=failures) as send, patch('backend.workers_proxy.time.sleep') as sleep:
                with self.assertRaises(APIError): self.p.speech('Test question')
            self.assertEqual(send.call_count, 2)
            sleep.assert_called_once_with(1)

    def test_capacity_retry_can_succeed(self):
        with patch.object(self.p.opener, 'open', side_effect=[HTTPError(ENDPOINT, 503, 'busy', {}, None), Response(b'ID3ok', 'audio/mpeg')]), patch('backend.workers_proxy.time.sleep'):
            self.assertEqual(self.p.speech('Test question'), b'ID3ok')

    def test_transport_failure_is_not_retried(self):
        for exc in (TimeoutError('private'), URLError('private')):
            with patch.object(self.p.opener, 'open', side_effect=exc) as send:
                with self.assertRaises(APIError): self.p.speech('Test question')
            self.assertEqual(send.call_count, 1)

    def test_oversized_and_invalid_envelopes(self):
        for value in (b'x'*(MAX_RESPONSE+1), b'not-json', [], {'success': False}, {'error': 'private'}, {'result': {'error': 'private'}}):
            with self.respond(value):
                with self.assertRaises(APIError): self.p.run(LLM_MODEL, {})

    def test_glm_choices_and_legacy_response_shapes(self):
        expected = {'question': 'How did you verify that?'}
        for result in ({'response': expected}, {'result': {'response': '```json\n'+json.dumps(expected)+'\n```'}}, {'choices': [{'finish_reason': 'stop', 'message': {'content': json.dumps(expected), 'reasoning_content': 'not used'}}]}):
            with self.respond(result) as send:
                self.assertEqual(self.p.structured('System', {'answer': 'untrusted'}, 'q', {}), expected)
            body = json.loads(send.call_args.args[0].data)
            self.assertEqual(body['model'], LLM_MODEL)
            self.assertFalse(body['input']['stream'])
            self.assertEqual(body['input']['messages'][1]['role'], 'user')

    def test_truncated_refused_and_invalid_json_rejected(self):
        for result in ({'choices': []}, {'choices': [{'finish_reason': 'length', 'message': {'content': '{}'}}]}, {'choices': [{'finish_reason': 'stop', 'message': {'content': '{}', 'refusal': 'no'}}]}, {'response': 'not JSON'}, {'response': []}):
            with self.respond(result):
                with self.assertRaises(APIError): self.p.structured('s', {}, 'q', {})

    def test_proxy_ai_keeps_question_validation(self):
        ai = ProxyAI()
        role = {'title': 'Test', 'details': 'Test', 'skills': []}
        with patch.object(ai.provider, 'structured', return_value={'question': 'x'}):
            with self.assertRaises(APIError): ai.next_question(role, [])

    def test_proxy_ai_keeps_evidence_validation_and_advisory_flag(self):
        ai = ProxyAI()
        role = {'title': 'Test', 'details': 'Test', 'skills': []}
        answers = [{'question': 'What changed?', 'answer': 'I measured impact.'}]
        names = ['Relevant experience', 'Problem solving', 'Evidence of impact']
        report = {'summary': 'Unverified claim.', 'criteria': [{'name': n, 'score': 3, 'reason': 'Example.', 'evidence': 'I measured impact.'} for n in names]}
        with patch.object(ai.provider, 'structured', return_value=report):
            result = ai.evaluate(role, answers)
        self.assertEqual(result['model'], LLM_MODEL)
        self.assertTrue(result['human_review_required'])
        self.assertEqual(result['score'], 60)
        report['criteria'][0]['evidence'] = 'Invented claim.'
        with patch.object(ai.provider, 'structured', return_value=report):
            with self.assertRaises(APIError): ai.evaluate(role, answers)

    def test_entrypoint_injects_proxy_without_direct_provider(self):
        with patch('backend.proxy_server.DurableInterviewApp') as app, patch('backend.server.CloudflareProvider', side_effect=AssertionError('No direct Cloudflare fallback')):
            create_app()
        self.assertIsInstance(app.call_args.kwargs['ai'].provider, WorkersProxyProvider)

    def test_entrypoint_missing_token_never_starts_app(self):
        with patch.dict(os.environ, {'PRATIK_WORKERS_AI_TOKEN': ''}), patch('backend.proxy_server.DurableInterviewApp') as app:
            with self.assertRaises(APIError): create_app()
        app.assert_not_called()
