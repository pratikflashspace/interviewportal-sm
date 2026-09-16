"""End-check must fail OPEN on provider failure so interviews cannot freeze.

Regression: on staging, Sarvam chat (sarvam-105b) rejects every structured
call, and the old code returned complete:false for provider failures - the
room stayed at 'Listening' forever and never asked the next question.
"""
import io
import json
import os
import tempfile
import unittest
from unittest.mock import patch

import test_backend as legacy
from backend.v2_endpoint import EvidenceOnlyAI
from backend.workspace_server import WorkspaceApp


class ProbeProvider:
    def __init__(self):
        self.behaviour = 'complete'
        self.calls = 0

    def structured(self, system, payload, name, schema):
        self.calls += 1
        if self.behaviour == 'raise':
            raise RuntimeError('synthetic provider outage')
        return {'decision': self.behaviour}


class EndCheckFailOpenTests(unittest.TestCase):
    """Isolated app: EvidenceOnlyAI with a controllable provider."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        env = patch.dict(os.environ, {'APP_ORIGIN': 'https://test.example',
                                      'CLICKUP_CANDIDATE_FOLDER_ID': '901612030752'})
        env.start()
        self.addCleanup(env.stop)
        self.provider = ProbeProvider()
        ai = object.__new__(EvidenceOnlyAI)
        ai.provider = self.provider
        self.app = WorkspaceApp(db_path=self.tmp.name + '/test.db', roles=[legacy.ROLE], ai=ai,
                                start_worker=False, recording_root=self.tmp.name + '/recordings')
        self.cookie = ''

    def req(self, path, body=None, origin=None):
        raw = json.dumps(body or {}).encode() if body is not None else b''
        envr = {'PATH_INFO': path, 'REQUEST_METHOD': 'POST' if body is not None else 'GET',
                'HTTP_ORIGIN': origin or self.app.origin, 'HTTP_X_REQUESTED_WITH': 'Flashspace',
                'CONTENT_TYPE': 'application/json', 'CONTENT_LENGTH': str(len(raw)),
                'wsgi.input': io.BytesIO(raw), 'HTTP_COOKIE': self.cookie, 'REMOTE_ADDR': 'synthetic'}
        result = {}
        headers = []

        def start(s, h):
            result['status'] = int(s.split()[0])
            headers.extend(h)
        out = b''.join(self.app(envr, start))
        result['body'] = json.loads(out) if out[:1] in (b'{', b'[', b'n') else out
        for k, v in headers:
            if k.lower() == 'set-cookie':
                self.cookie = v.split(';')[0]
        return result

    def signup(self):
        r = self.req('/api/auth/candidate/signup', {'name': 'Fail Open Candidate',
                     'email': 'failopen@example.com', 'password': 'test-password-long',
                     'confirm_password': 'test-password-long', 'phone': '9876543210'})
        self.assertEqual(r['status'], 200, r)

    def new_application(self):
        with self.app.store.db() as db:
            db.execute('INSERT INTO settings(key,value) VALUES (?,?)', ('v2-bank:growth', 'sales'))
        r = self.req('/api/v2/applications', {'role_id': 'growth',
                     'experience': 'Synthetic fail-open regression experience.',
                     'consent': True, 'consent_version': 'flashspace-sarvam-conversation-v2'})
        self.assertEqual(r['status'], 200, r)
        return r['body']

    def end_check(self, f, answer):
        return self.req('/api/v2/applications/' + f['application_id'] + '/end-check',
                        {'question_id': f['active']['id'], 'version': f['version'], 'answer': answer})

    def test_provider_failure_fails_open(self):
        self.signup()
        f = self.new_application()
        self.provider.behaviour = 'raise'
        r = self.end_check(f, 'A finished answer that clearly ends.')
        self.assertEqual(r['status'], 200, r)
        self.assertTrue(r['body']['complete'], 'provider failure must fail open, not freeze the interview')
        self.assertGreaterEqual(self.provider.calls, 1)

    def test_model_uncertain_still_waits(self):
        self.signup()
        f = self.new_application()
        self.provider.behaviour = 'uncertain'
        r = self.end_check(f, 'Hmm, let me think about it, I will continue in a moment.')
        self.assertEqual(r['status'], 200, r)
        self.assertFalse(r['body']['complete'], 'a genuine model judgment of uncertain must still wait')

    def test_model_complete_still_completes(self):
        self.signup()
        f = self.new_application()
        self.provider.behaviour = 'complete'
        r = self.end_check(f, 'That is the whole story.')
        self.assertEqual(r['status'], 200, r)
        self.assertTrue(r['body']['complete'])


if __name__ == '__main__':
    unittest.main()
