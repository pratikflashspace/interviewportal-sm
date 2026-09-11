"""Real PostgreSQL tests for the opt-in staging app; no external AI or sync.

TEST_POSTGRES_URL must identify a disposable test database, never production.
Each test uses a unique schema. App recreation tests persistence, not a real
Render restart or machine/process kill.
"""
import io
import json
import os
import unittest
import uuid
from unittest.mock import patch

from backend.durable_server import DurableInterviewApp
from test_postgres_integration import schema_test_url

ROLE = {
    'id': 'durable-test', 'title': 'Test role', 'department': 'Test',
    'location': 'Remote', 'type': 'Full-time', 'experience': 'Any',
    'description': 'Fictional test role', 'details': 'Test requirements',
    'skills': ['Testing'], 'published': True,
}
ANSWER = 'I measured completed workflows against the baseline.'


class FakeAI:
    def __init__(self):
        self.calls = 0
        self.failure = None
        self.before_reply = None

    def next_question(self, role, answers):
        self.calls += 1
        if self.before_reply:
            self.before_reply(answers)
        if self.failure:
            raise self.failure
        return 'How did you verify the measured improvement?'


@unittest.skipUnless(os.getenv('TEST_POSTGRES_URL'), 'No disposable Postgres test connection configured')
class DurablePostgresTests(unittest.TestCase):
    def setUp(self):
        import psycopg
        from psycopg import sql
        self.url = os.environ['TEST_POSTGRES_URL']
        self.schema = 'fs_durable_' + uuid.uuid4().hex
        with psycopg.connect(self.url, autocommit=True) as conn:
            conn.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(self.schema)))
        self.addCleanup(self.drop_schema)
        self.env = patch.dict(os.environ, {
            'DATABASE_URL': schema_test_url(self.url, self.schema),
            'ADMIN_EMAIL': '', 'REQUIRE_DATABASE_URL': '', 'RENDER': '',
            'APP_ORIGIN': 'http://localhost:8000', 'RENDER_EXTERNAL_URL': '',
            'MAX_AI_CALLS_PER_DAY': '100',
        })
        self.env.start()
        self.addCleanup(self.env.stop)
        self.ai = FakeAI()
        self.app = self.new_app()
        self.cookie = ''
        self.req('/api/register', {
            'email': 'durable@example.com', 'name': 'Fictional Candidate',
            'password': 'OnlyForDisposableTests123!',
        })
        self.application = self.req('/api/applications', {
            'role_id': ROLE['id'], 'experience': 'A fictional workflow improvement for testing.',
            'portfolio': '', 'consent': True,
        })
        self.path = f"/api/applications/{self.application['id']}/answer"
        self.body = {'turn': 0, 'answer': ANSWER}

    def drop_schema(self):
        import psycopg
        from psycopg import sql
        with psycopg.connect(self.url, autocommit=True) as conn:
            conn.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(self.schema)))

    def new_app(self):
        app = DurableInterviewApp(roles=[ROLE], ai=self.ai, start_worker=False)
        self.assertTrue(app.store.is_postgres)
        return app

    def req(self, path, body=None, expected=200):
        data = json.dumps(body).encode() if body is not None else b''
        result = {}
        def start(status, headers):
            result['status'] = int(status.split()[0])
            result['headers'] = dict(headers)
        raw = b''.join(self.app({
            'REQUEST_METHOD': 'POST' if body is not None else 'GET',
            'PATH_INFO': path, 'HTTP_COOKIE': self.cookie,
            'HTTP_ORIGIN': self.app.origin, 'HTTP_X_REQUESTED_WITH': 'Flashspace',
            'CONTENT_TYPE': 'application/json', 'CONTENT_LENGTH': str(len(data)),
            'wsgi.input': io.BytesIO(data),
        }, start))
        if result['headers'].get('Set-Cookie'):
            self.cookie = result['headers']['Set-Cookie'].split(';')[0]
        self.assertEqual(result['status'], expected, raw.decode())
        return json.loads(raw)

    def resume(self):
        self.app = self.new_app()
        applications = self.req('/api/applications')
        self.assertEqual(len(applications), 1)
        self.assertEqual(applications[0]['id'], self.application['id'])
        return applications[0]

    def test_answer_commits_before_ai_and_survives_app_recreation(self):
        observed = []
        def inspect(answers):
            # The other app reads via independent PostgreSQL connections.
            reader = self.new_app()
            saved = reader.store.get(self.application['id'])
            observed.append(saved)
        self.ai.before_reply = inspect
        reply = self.req(self.path, self.body)
        self.assertEqual(len(observed), 1)
        self.assertEqual(observed[0]['answers'][0]['answer'], ANSWER)
        self.assertEqual(observed[0]['question_source'], 'standard')
        self.assertEqual(reply['question_source'], 'ai')
        saved = self.resume()
        self.assertEqual(saved['answers'], reply['answers'])
        self.assertEqual(saved['question'], reply['question'])
        self.assertEqual(saved['question_source'], 'ai')

    def test_provider_failure_resume_and_retry_preserve_one_answer(self):
        self.ai.failure = RuntimeError('Synthetic provider failure')
        reply = self.req(self.path, self.body)
        self.assertEqual(reply['question_source'], 'standard')
        self.assertTrue(reply['question'].startswith('Standard follow-up:'))
        saved = self.resume()
        self.assertEqual(saved['answers'], reply['answers'])
        self.ai.failure = None
        with patch.object(self.app, 'ai_quota', side_effect=AssertionError('Retry must not spend quota')):
            retried = self.req(self.path, self.body)
        self.assertEqual(len(retried['answers']), 1)
        self.assertEqual(retried['question'], reply['question'])
        self.assertEqual(self.ai.calls, 1)
        self.req(self.path, {'turn': 0, 'answer': 'A different conflicting answer.'}, expected=409)
        self.assertEqual(len(self.app.store.get(self.application['id'])['answers']), 1)

    def test_simulated_interruption_after_commit_is_recoverable(self):
        # SystemExit bypasses Exception handlers; this is not an OS-level kill.
        self.ai.failure = SystemExit('Synthetic interruption')
        with self.assertRaises(SystemExit):
            self.req(self.path, self.body)
        saved = self.resume()
        self.assertEqual(len(saved['answers']), 1)
        self.assertEqual(saved['answers'][0]['answer'], ANSWER)
        self.assertEqual(saved['question_source'], 'standard')
        self.ai.failure = None
        self.req(self.path, self.body)
        self.assertEqual(self.ai.calls, 1)

    def test_first_database_write_failure_returns_error_without_ai(self):
        import psycopg
        with patch.object(self.app.store, 'save', side_effect=psycopg.OperationalError('Synthetic write failure')):
            self.req(self.path, self.body, expected=500)
        self.assertEqual(self.ai.calls, 0)
        self.assertEqual(self.resume()['answers'], [])
        self.assertEqual(len(self.req(self.path, self.body)['answers']), 1)

    def test_second_database_write_failure_preserves_committed_fallback(self):
        import psycopg
        original = self.app.store.save
        writes = []
        def fail_second(application):
            writes.append(application['question_source'])
            if len(writes) == 2:
                raise psycopg.OperationalError('Synthetic second write failure')
            return original(application)
        with patch.object(self.app.store, 'save', side_effect=fail_second):
            self.req(self.path, self.body, expected=500)
        self.assertEqual(writes, ['standard', 'ai'])
        saved = self.resume()
        self.assertEqual(len(saved['answers']), 1)
        self.assertEqual(saved['question_source'], 'standard')
        self.assertTrue(saved['question'].startswith('Standard follow-up:'))
        self.req(self.path, self.body)
        self.assertEqual(self.ai.calls, 1)
