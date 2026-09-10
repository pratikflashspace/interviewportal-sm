"""Mocked Sarvam contracts/security and WSGI integration; no live API calls."""
import base64
import io
import json
import os
import tempfile
import unittest
from email.parser import BytesParser
from email.policy import default
from unittest.mock import patch
from urllib.error import HTTPError, URLError
from urllib.request import Request
import test_backend as legacy
from backend.server import APIError
from backend.durable_server import DurableInterviewApp
from backend.sarvam_server import SarvamAI, create_app
from backend.sarvam_provider import (
    SarvamProvider, NoRedirect, ORIGIN, CHAT_PATH, STT_PATH, TTS_PATH,
    LLM_MODEL, STT_MODEL, TTS_MODEL, MAX_AUDIO, MAX_RESPONSE,
)

SCHEMA = {'type': 'object', 'properties': {'question': {'type': 'string'}},
          'required': ['question'], 'additionalProperties': False}
NAMES = ['Relevant experience', 'Problem solving', 'Evidence of impact']


def chat(value, finish='stop', **message):
    return {'choices': [{'finish_reason': finish, 'message': {
        'content': json.dumps(value), **message,
    }}]}


def report(quote='I measured impact.'):
    return {'summary': 'Unverified claims; human review required.', 'criteria': [
        {'name': n, 'score': 3, 'reason': 'Relevant example.', 'evidence': quote} for n in NAMES
    ]}


class Response:
    def __init__(self, value):
        self.raw = value if isinstance(value, bytes) else json.dumps(value).encode()
    def read(self, limit): return self.raw[:limit]
    def __enter__(self): return self
    def __exit__(self, *args): pass


class SarvamTests(unittest.TestCase):
    def setUp(self):
        env = patch.dict(os.environ, {'SARVAM_API_KEY': 'synthetic-test-only'})
        env.start()
        self.addCleanup(env.stop)
        self.p = SarvamProvider(APIError)

    def respond(self, value):
        return patch.object(self.p.opener, 'open', return_value=Response(value))

    def test_missing_or_unsafe_key(self):
        for token in ('', 'Bearer abc', 'a\nb', '\"abc\"', "'abc'", 'a\x00b', 'é'):
            with self.subTest(token=repr(token)), patch.dict(os.environ, {'SARVAM_API_KEY': token}):
                with self.assertRaises(APIError): SarvamProvider(APIError)

    def test_endpoint_guard_and_redirect(self):
        with patch.object(self.p.opener, 'open') as send:
            with self.assertRaises(APIError): self.p._send('https://evil.example', b'{}')
            send.assert_not_called()
        self.assertIsNone(NoRedirect().redirect_request(Request(ORIGIN), None, 302, '', {}, 'https://evil.example'))

    def test_chat_wire_contract(self):
        expected = {'question': 'How did you measure success?'}
        with self.respond(chat(expected, reasoning_content='Do not use this.')) as send:
            self.assertEqual(self.p.structured('system', {'answer': 'untrusted'}, 'question', SCHEMA), expected)
        req = send.call_args.args[0]
        body = json.loads(req.data)
        self.assertEqual(req.full_url, ORIGIN + CHAT_PATH)
        self.assertEqual(req.get_header('Api-subscription-key'), 'synthetic-test-only')
        self.assertIsNone(req.get_header('Authorization'))
        self.assertEqual(body['model'], LLM_MODEL)
        self.assertTrue(body['response_format']['json_schema']['strict'])
        self.assertEqual(body['response_format']['json_schema']['schema'], SCHEMA)
        self.assertIsNone(body['reasoning_effort'])
        self.assertFalse(body['stream'])
        self.assertEqual(body['n'], 1)
        self.assertEqual(body['messages'][1]['role'], 'user')
        self.assertEqual(send.call_args.kwargs['timeout'], 40)

    def test_incomplete_chat_rejected(self):
        values = [{'choices': []}, {'choices': [None]}, chat({}, finish='length'),
                  chat({}, refusal='no'), chat({}, tool_calls=[{}]),
                  {'choices': [{'finish_reason': 'stop', 'message': {'content': None, 'reasoning_content': '{}'}}]}]
        for value in values:
            with self.subTest(value=value), self.respond(value):
                with self.assertRaises(APIError): self.p.structured('s', {}, 'question', SCHEMA)

    def test_schema_and_json_rejected(self):
        for value in ({}, [], {'question': 4}, {'question': 'valid', 'extra': True}):
            with self.respond(chat(value)):
                with self.assertRaises(APIError): self.p.structured('s', {}, 'question', SCHEMA)
        for content in ('not JSON', '```json\n{}\n```'):
            with self.respond(chat({}, content=content)):
                with self.assertRaises(APIError): self.p.structured('s', {}, 'question', SCHEMA)

    def test_stt_multipart_contract_all_browser_formats(self):
        data = bytes(range(256))
        for mime in ('audio/webm;codecs=opus', 'audio/mp4', 'audio/ogg', 'audio/wav', 'audio/mpeg'):
            with self.subTest(mime=mime), self.respond({'transcript': ' A useful answer. '}) as send:
                self.assertEqual(self.p.transcribe(data, mime), {'text': 'A useful answer.'})
            req = send.call_args.args[0]
            self.assertEqual(req.full_url, ORIGIN + STT_PATH)
            msg = BytesParser(policy=default).parsebytes(('Content-Type: ' + req.get_header('Content-type') + '\r\nMIME-Version: 1.0\r\n\r\n').encode() + req.data)
            parts = {p.get_param('name', header='content-disposition'): p for p in msg.iter_parts()}
            self.assertEqual(parts['file'].get_payload(decode=True), data)
            self.assertEqual(parts['model'].get_content().strip(), STT_MODEL)
            self.assertEqual(parts['mode'].get_content().strip(), 'transcribe')
            self.assertEqual(parts['language_code'].get_content().strip(), 'unknown')
            self.assertEqual(parts['file'].get_content_type(), mime.split(';')[0])

    def test_stt_preflight_and_empty_transcript(self):
        with patch.object(self.p.opener, 'open') as send:
            for data, mime in ((b'a'*99, 'audio/webm'), (b'a'*(MAX_AUDIO+1), 'audio/webm'), (b'a'*100, 'text/plain')):
                with self.assertRaises(APIError): self.p.transcribe(data, mime)
            send.assert_not_called()
        for text in (' ', 'x'*6001, None):
            with self.respond({'transcript': text}):
                with self.assertRaises(APIError): self.p.transcribe(b'a'*100, 'audio/webm')

    def test_tts_wire_contract(self):
        audio = b'ID3mock-audio'
        with self.respond({'audios': [base64.b64encode(audio).decode()]}) as send:
            self.assertEqual(self.p.speech('Tell me about your work.'), audio)
        req = send.call_args.args[0]
        body = json.loads(req.data)
        self.assertEqual(req.full_url, ORIGIN + TTS_PATH)
        self.assertEqual(body['model'], TTS_MODEL)
        self.assertEqual(body['output_audio_codec'], 'mp3')
        self.assertEqual(body['language_code'], 'en-IN')
        self.assertEqual(body['speaker'], 'shubh')
        self.assertNotIn('pitch', body)
        self.assertNotIn('loudness', body)

    def test_tts_invalid_audio_and_questions(self):
        for audios in ([], ['bad!'], [''], [base64.b64encode(b'RIFFnot-mp3').decode()], ['a', 'b'], None):
            with self.respond({'audios': audios}):
                with self.assertRaises(APIError): self.p.speech('Test question')
        with patch.object(self.p.opener, 'open') as send:
            for q in ('', ' ', 'x'*651, None):
                with self.assertRaises(APIError): self.p.speech(q)
            send.assert_not_called()

    def test_http_failures_sanitized_no_retry(self):
        for code in (301, 302, 307, 308, 400, 401, 402, 403, 413, 422, 429, 500, 503):
            exc = HTTPError(ORIGIN, code, 'synthetic-test-only private', {}, io.BytesIO(b'private body'))
            with patch.object(self.p.opener, 'open', side_effect=exc) as send:
                with self.assertRaises(APIError) as caught: self.p.speech('Test question')
            self.assertEqual(send.call_count, 1)
            self.assertNotIn('synthetic-test-only', caught.exception.message)
            self.assertNotIn('private', caught.exception.message)

    def test_transport_failures_no_retry(self):
        for exc in (TimeoutError('private'), URLError('private'), OSError('private')):
            with patch.object(self.p.opener, 'open', side_effect=exc) as send:
                with self.assertRaises(APIError): self.p.speech('Test question')
            self.assertEqual(send.call_count, 1)

    def test_invalid_envelopes_and_size_limit(self):
        for value in (b'x'*(MAX_RESPONSE+1), b'not-json', [], {'error': 'private'}, {'success': False}):
            with self.respond(value):
                with self.assertRaises(APIError): self.p._send(CHAT_PATH, b'{}')

    def test_question_and_report_semantic_validation(self):
        ai = SarvamAI()
        with patch.object(ai.provider.opener, 'open', return_value=Response(chat({'question': 'x'}))):
            with self.assertRaises(APIError): ai.next_question(legacy.ROLE, [])
        with patch.object(ai.provider.opener, 'open', return_value=Response(chat(report()))):
            result = ai.evaluate(legacy.ROLE, [{'answer': 'I measured impact.'}])
        self.assertEqual(result['score'], 60)
        self.assertTrue(result['human_review_required'])
        self.assertEqual(result['model'], LLM_MODEL)
        self.assertEqual(result['provider'], 'sarvam')
        self.assertEqual(result['rubric_version'], 'flashspace-sarvam-v1')
        for invalid in (report('invented quote'), {**report(), 'criteria': [None]*3}):
            with patch.object(ai.provider.opener, 'open', return_value=Response(chat(invalid))):
                with self.assertRaises(APIError): ai.evaluate(legacy.ROLE, [{'answer': 'I measured impact.'}])
        with patch.object(ai.provider.opener, 'open', return_value=Response(chat(report('')))):
            self.assertEqual(ai.evaluate(legacy.ROLE, [{'answer': 'I measured impact.'}])['score'], 0)

    def test_boolean_score_is_not_integer(self):
        ai = SarvamAI()
        value = report()
        value['criteria'][0]['score'] = True
        with patch.object(ai.provider.opener, 'open', return_value=Response(chat(value))):
            with self.assertRaises(APIError): ai.evaluate(legacy.ROLE, [{'answer': 'I measured impact.'}])

    def test_entrypoint_no_cloudflare_fallback(self):
        with patch('backend.sarvam_server.DurableInterviewApp') as app, patch('backend.server.CloudflareProvider', side_effect=AssertionError('No fallback')):
            create_app()
        self.assertIsInstance(app.call_args.kwargs['ai'].provider, SarvamProvider)
        with patch.dict(os.environ, {'SARVAM_API_KEY': ''}), patch('backend.sarvam_server.DurableInterviewApp') as app:
            with self.assertRaises(APIError): create_app()
        app.assert_not_called()


class SarvamFlowTests(unittest.TestCase):
    req = legacy.BackendTests.req
    register = legacy.BackendTests.register
    apply = legacy.BackendTests.apply

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        env = patch.dict(os.environ, {'SARVAM_API_KEY': 'synthetic-test-only', 'ADMIN_EMAIL': '', 'APP_ORIGIN': 'http://localhost:8000'})
        env.start()
        self.addCleanup(env.stop)
        self.ai = SarvamAI()
        self.cu = legacy.FakeClickUp()
        self.path = self.temp.name + '/sarvam.db'
        self.app = DurableInterviewApp(self.path, [legacy.ROLE], self.ai, self.cu, False)
        self.cookie = ''
        self.network = patch.object(self.ai.provider.opener, 'open', side_effect=AssertionError('Unmocked network'))
        self.network.start()
        self.addCleanup(self.network.stop)

    def test_complete_interview_voice_report_and_sync(self):
        self.register()
        a = self.apply()
        path = '/api/applications/' + a['id']
        with patch.object(self.ai.provider.opener, 'open', return_value=Response({'audios': [base64.b64encode(b'ID3mock').decode()]})):
            speech = self.req(path + '/speech', {})
        self.assertEqual(speech['status'], 200)
        self.assertEqual(speech['headers']['Content-Type'], 'audio/mpeg')
        self.assertEqual(speech['body'], b'ID3mock')
        with patch.object(self.ai.provider.opener, 'open', return_value=Response({'transcript': 'I measured impact.'})):
            self.assertEqual(self.req(path + '/transcribe', b'a'*100, raw=True)['body']['text'], 'I measured impact.')
        with patch.object(self.ai.provider.opener, 'open', return_value=Response(chat({'question': 'How did you measure that impact?'}))) as send:
            for turn in range(4):
                self.assertEqual(self.req(path + '/answer', {'turn': turn, 'answer': 'I measured impact.'})['status'], 200)
            self.assertEqual(send.call_count, 3)
            self.assertEqual(self.req(path + '/answer', {'turn': 3, 'answer': 'I measured impact.'})['status'], 200)
            self.assertEqual(send.call_count, 3)
        self.assertEqual(self.req(path + '/finish', {})['status'], 200)
        with patch.object(self.ai.provider.opener, 'open', return_value=Response(chat(report()))) as send:
            self.app.work_once()
            self.app.work_once()
            self.assertEqual(send.call_count, 1)
        self.assertEqual(self.cu.records[-1]['evaluation']['provider'], 'sarvam')
        self.assertEqual(len(self.cu.records[-1]['answers']), 4)
        shown = self.req('/api/applications')['body'][0]
        self.assertNotIn('evaluation', shown)
        self.assertEqual(shown['sync_status'], 'Synced')

    def test_provider_failure_commit_restart_and_retry(self):
        self.register()
        a = self.apply()
        def fail(req, **kwargs):
            self.assertEqual(len(self.app.store.get(a['id'])['answers']), 1)
            raise HTTPError(ORIGIN, 403, 'private', {}, None)
        with patch.object(self.ai.provider.opener, 'open', side_effect=fail) as send:
            body = {'turn': 0, 'answer': 'I measured impact.'}
            response = self.req('/api/applications/' + a['id'] + '/answer', body)
            self.assertEqual(response['status'], 200)
            self.assertEqual(response['body']['question_source'], 'standard')
            self.assertEqual(self.req('/api/applications/' + a['id'] + '/answer', body)['status'], 200)
            self.assertEqual(send.call_count, 1)
        restarted = DurableInterviewApp(self.path, [legacy.ROLE], self.ai, self.cu, False)
        self.assertEqual(len(restarted.store.get(a['id'])['answers']), 1)

    def test_cross_candidate_audio_denied_without_network(self):
        self.register()
        a = self.apply()
        self.register('other@example.com')
        path = '/api/applications/' + a['id']
        self.assertEqual(self.req(path + '/speech', {})['status'], 404)
        self.assertEqual(self.req(path + '/transcribe', b'a'*100, raw=True)['status'], 404)
