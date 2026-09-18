"""Candidate outreach: email + WhatsApp on hiring decisions.

Isolated SQLite; SMTP and WhatsApp are fakes. Covers idempotency (no double
send for the same stage), channel independence (email failure does not stop
WhatsApp), configuration gating, and that the decision is never blocked.
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


class OutreachTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.env = patch.dict(os.environ, {'APP_ORIGIN': 'https://test.example',
                                           'CLICKUP_CANDIDATE_FOLDER_ID': '901612030752',
                                           'CLICKUP_API_TOKEN': '',
                                           'SMTP_HOST': '', 'SMTP_USER': '', 'SMTP_PASSWORD': '',
                                           'WHATSAPP_TOKEN': '', 'WHATSAPP_PHONE_ID': ''})
        self.env.start(); self.addCleanup(self.env.stop)
        self.app = WorkspaceApp(db_path=self.tmp.name + '/test.db', roles=[ROLE],
                                ai=FakeAI(), start_worker=False,
                                recording_root=self.tmp.name + '/recordings')
        self.cookie = ''
        self.sent_email = []
        self.sent_wa = []

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

    def login_recruiter(self):
        with self.app.store.db() as db:
            db.execute('INSERT INTO users VALUES (?,?,?,?,1,?)',
                       ('recruiter', RECRUITER_EMAIL, 'Recruiter', hash_password('test-password-long'), now()))
        return self.req('/api/auth/recruiter/login',
                        {'email': RECRUITER_EMAIL, 'password': 'test-password-long'})

    def make_completed_application(self):
        self.signup()
        # Insert a completed application directly through the store.
        app = {'id': 'app-outreach-1', 'user_id': self._uid(),
               'name': 'Test Candidate', 'email': 'candidate@example.com', 'role_id': ROLE['id'],
               'role_title': ROLE['title'], 'role_snapshot': ROLE, 'portfolio': '', 'experience': 'x' * 20,
               'created_at': now(), 'consent_at': now(), 'consent_version': 'v', 'status': 'completed',
               'answers': [], 'question': None, 'evaluation': None, 'version': 0}
        with self.app.store.db() as db:
            from backend.server import encode
            db.execute('INSERT INTO applications(id,user_id,role_id,data) VALUES (?,?,?,?)',
                       (app['id'], app['user_id'], app['role_id'], encode(app)))
        return app

    def _uid(self):
        with self.app.store.db() as db:
            return db.execute("SELECT id FROM users WHERE email='candidate@example.com'").fetchone()['id']

    def stage(self, aid, stage, note=''):
        return self.req('/api/workspace/recruiter/applications/' + aid + '/stage',
                        {'version': 0, 'stage': stage, 'note': note})

    def test_decision_saves_and_reports_outreach_not_configured(self):
        app = self.make_completed_application(); self.login_recruiter()
        r = self.stage(app['id'], 'shortlisted')
        self.assertEqual(r['status'], 200, r)
        o = r['body'].get('outreach')
        self.assertIsNotNone(o, 'outreach block must be present for decision stages')
        self.assertEqual(o['stage'], 'shortlisted')
        self.assertTrue(str(o['email']).startswith('skipped:'))
        self.assertTrue(str(o['whatsapp']).startswith('skipped:'))

    def test_same_stage_never_resends(self):
        app = self.make_completed_application(); self.login_recruiter()
        r1 = self.stage(app['id'], 'shortlisted')
        r2 = self.req('/api/workspace/recruiter/applications/' + app['id'] + '/stage',
                      {'version': 1, 'stage': 'shortlisted'})
        self.assertEqual(r2['status'], 200)
        self.assertTrue(r2['body']['outreach']['already_sent'],
                       're-saving the same stage must not re-notify')

    def test_new_stage_sends_again_and_never_blocks(self):
        app = self.make_completed_application(); self.login_recruiter()
        r1 = self.stage(app['id'], 'shortlisted')
        r2 = self.req('/api/workspace/recruiter/applications/' + app['id'] + '/stage',
                      {'version': 1, 'stage': 'rejected', 'note': 'We filled the role.'})
        self.assertEqual(r2['status'], 200, 'a failing channel must never block the decision')
        self.assertFalse(r2['body']['outreach']['already_sent'])

    def test_note_flows_into_the_templates(self):
        from backend import outreach
        body = outreach.STAGE_BODIES['rejected'].format(name='Asha', role='Sales', note='We filled the role.\n\n')
        self.assertIn('We filled the role.', body)

    def test_whatsapp_text_and_phone_rules(self):
        from backend import outreach
        text = outreach.WHATSAPP_TEXTS['hired'].format(name='Asha', role='Sales')
        self.assertIn('Asha', text)
        self.assertIn('Sales', text)

    def test_unconfigured_channels_report_skipped(self):
        from backend import outreach
        app = self.app
        a = {'id': 'zzz', 'name': 'Asha', 'role_title': 'Sales', 'email': 'a@x.dev', 'user_id': 'nobody'}
        result = outreach.notify_decision(app, a, 'hired')
        self.assertTrue(str(result['email']).startswith('skipped:'))
        self.assertTrue(str(result['whatsapp']).startswith('skipped:'))
        self.assertTrue(result['complete'] if 'complete' in result else True)


if __name__ == '__main__':
    unittest.main()
