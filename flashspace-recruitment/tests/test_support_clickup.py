"""Support queue ClickUp sync: one flat list, one task per candidate query.

Real WSGI requests against isolated SQLite; ClickUp is a recorded fake so no
external service is contacted. Covers the candidate POST sync, the recruiter
reply update, and that a ClickUp failure never blocks the candidate.
"""
import io
import json
import os
import tempfile
import unittest
from unittest.mock import patch
from backend.workspace_server import WorkspaceApp
from backend.server import now, hash_password
from test_backend import FakeAI, ROLE

RECRUITER_EMAIL = 'team@stirringminds.com'


class RecordingClickUp:
    """Minimal ClickUp double that records every call and serves an id."""

    def __init__(self, store):
        self.store = store
        self.calls = []

    def call(self, method, path, data=None):
        self.calls.append((method, path, data))
        if method == 'GET' and path.startswith('folder/'):
            return {'id': '901612030752', 'name': 'Teamrecrut - Candidates',
                    'space': {'id': '90161257650', 'name': 'FlashSpace'}}
        if method == 'GET' and 'folder' in path and '/list' in path:
            return {'lists': []}
        if method == 'GET' and path.startswith('space/'):
            return {'folders': []}
        if method == 'GET' and '/task' in path:
            return {'tasks': []}
        if method == 'POST':
            # Real ClickUp ids are numeric; the production cache validates that.
            kind = 'folder' if '/folder' in path else 'list' if '/list' in path else 'task'
            base = {'folder': '90161300000', 'list': '90161400000', 'task': '90161500000'}[kind]
            nid = str(int(base) + len(self.calls))
            return {'id': nid, 'url': 'https://clickup.example/t/' + nid}
        if method == 'PUT':
            return {'id': '90161599999', 'url': 'https://clickup.example/t/90161599999'}
        raise AssertionError('unexpected call', method, path)


class FailingClickUp(RecordingClickUp):
    def call(self, method, path, data=None):
        from backend.server import APIError
        raise APIError(503, 'ClickUp is not configured. Record saved; sync pending.')


class SupportQueueTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.env = patch.dict(os.environ, {'APP_ORIGIN': 'https://test.example',
                                           'CLICKUP_CANDIDATE_FOLDER_ID': '901612030752',
                                           'CLICKUP_API_TOKEN': ''})
        self.env.start(); self.addCleanup(self.env.stop)
        self.app = WorkspaceApp(db_path=self.tmp.name + '/test.db', roles=[ROLE],
                                ai=FakeAI(), start_worker=False,
                                recording_root=self.tmp.name + '/recordings')
        self.cookie = ''

    def req(self, path, body=None, cookie=None):
        raw = json.dumps(body).encode() if body is not None else b''
        result = {}
        env = {'PATH_INFO': path, 'REQUEST_METHOD': 'POST' if body is not None else 'GET',
               'HTTP_ORIGIN': self.app.origin, 'HTTP_X_REQUESTED_WITH': 'Flashspace',
               'CONTENT_TYPE': 'application/json', 'CONTENT_LENGTH': str(len(raw)),
               'wsgi.input': io.BytesIO(raw),
               'HTTP_COOKIE': self.cookie if cookie is None else cookie, 'REMOTE_ADDR': 'synthetic'}
        def start(status, headers):
            result['status'] = int(status.split()[0]); result['headers'] = headers
        result['body'] = json.loads(b''.join(self.app(env, start)))
        for k, v in result['headers']:
            if k == 'Set-Cookie': self.cookie = v.split(';')[0]
        return result

    def signup(self, email='candidate@example.com'):
        return self.req('/api/auth/candidate/signup',
                        {'name': 'Test Candidate', 'email': email, 'password': 'test-password-long',
                         'confirm_password': 'test-password-long', 'phone': '9876543210'})

    def install(self, double):
        self.app.support_clickup.clickup = double(self.app.store)

    def test_candidate_query_creates_one_clickup_task(self):
        self.signup(); self.install(RecordingClickUp)
        r = self.req('/api/workspace/support', {'subject': 'Audio issue',
                                                 'message': 'The interviewer voice is not audible on my phone.'})
        self.assertEqual(r['status'], 200, r)
        posts = [c for c in self.app.support_clickup.clickup.calls if c[0] == 'POST' and '/task' in c[1]]
        self.assertEqual(len(posts), 1, 'exactly one task created per query')
        name, desc = posts[0][2]['name'], posts[0][2]['description']
        self.assertIn('Audio issue', name)
        self.assertIn('Test Candidate', name)
        self.assertIn('The interviewer voice is not audible', desc)
        self.assertIn('candidate@example.com', desc)

    def test_recruiter_reply_updates_the_existing_task(self):
        self.signup(); self.install(RecordingClickUp)
        tid = self.req('/api/workspace/support', {'subject': 'Audio issue',
                        'message': 'Synthetic support ticket for testing'})['body']['id']
        with self.app.store.db() as db:
            db.execute('INSERT INTO users VALUES (?,?,?,?,1,?)',
                       ('recruiter', RECRUITER_EMAIL, 'Recruiter', hash_password('test-password-long'), now()))
        self.req('/api/auth/recruiter/login', {'email': RECRUITER_EMAIL, 'password': 'test-password-long'})
        r = self.req('/api/workspace/recruiter/support/' + tid,
                     {'reply': 'Please check microphone permissions.', 'status': 'resolved'})
        self.assertEqual(r['status'], 200, r)
        puts = [c for c in self.app.support_clickup.clickup.calls if c[0] == 'PUT' and 'task/' in c[1]]
        self.assertEqual(len(puts), 1, 'reply updates the existing task, no duplicate')
        self.assertIn('Please check microphone permissions.', puts[0][2]['description'])

    def test_clickup_outage_never_blocks_the_candidate(self):
        self.signup(); self.install(FailingClickUp)
        r = self.req('/api/workspace/support', {'subject': 'Audio issue',
                                                 'message': 'Synthetic support ticket for testing'})
        self.assertEqual(r['status'], 200, r)
        rows = self.req('/api/workspace/support')['body']
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['status'], 'open')

    def test_retry_after_outage_uses_same_task_name(self):
        self.signup(); self.install(FailingClickUp)
        self.req('/api/workspace/support', {'subject': 'Audio issue',
                                             'message': 'Synthetic support ticket for testing'})
        self.install(RecordingClickUp)
        # The next request triggers a fresh sync attempt of any pending ticket
        # only through explicit paths; this test asserts idempotence: syncing
        # the same ticket twice must not create two tasks (find-or-create).
        ticket = self.req('/api/workspace/support')['body'][0]
        self.assertIsNone(self.app.support_clickup._setting('support-task:' + ticket['id']),
                          'failed sync must not cache a task id')
        self.app.support_clickup.sync_ticket({'id': ticket['id'], 'user_id': 'u1', 'name': 'Test Candidate',
                                              'email': 'candidate@example.com', 'subject': ticket['subject'],
                                              'message': ticket['message'], 'status': 'open', 'reply': '',
                                              'created': ticket['created']})
        created = [c for c in self.app.support_clickup.clickup.calls if c[0] == 'POST' and '/task' in c[1]]
        self.assertEqual(len(created), 1)
        # A second sync of the same ticket updates, not duplicates.
        self.app.support_clickup.sync_ticket({'id': ticket['id'], 'user_id': 'u1', 'name': 'Test Candidate',
                                              'email': 'candidate@example.com', 'subject': ticket['subject'],
                                              'message': ticket['message'], 'status': 'open', 'reply': 'still open',
                                              'created': ticket['created']})
        created2 = [c for c in self.app.support_clickup.clickup.calls if c[0] == 'POST' and '/task' in c[1]]
        self.assertEqual(len(created2), 1, 'cached task id must prevent a second create')


if __name__ == '__main__':
    unittest.main()
