"""Custom domains fronting the service are trusted for same-origin POSTs via APP_EXTRA_ORIGINS.

Regression: the candidate site moved to https://recrut.teamlens.co while the service
still reports its Render URL. The old single-origin CSRF check rejected every write
(signup, login, apply, answers) on the custom domain with 403.
"""
import io
import json
import os
import unittest
from unittest.mock import patch

from backend.server import App


ROLE = {'id': 'growth', 'title': 'Growth', 'department': 'Growth', 'location': 'New Delhi',
        'type': 'Full-time', 'experience': '1-3', 'description': 'd', 'details': 'd',
        'skills': ['Sales'], 'published': True}


class FakeAI:
    def next_question(self, role, answers): return 'Q'
    def evaluate(self, role, answers): return {'summary': 's'}


class FakeClickUp:
    def sync(self, a): return 'task', 'url'


class ExtraOriginTests(unittest.TestCase):
    def build(self, tempdir):
        return App(tempdir + '/extra.db', [ROLE], FakeAI(), FakeClickUp(), False)

    def req(self, app, path, body, origin=None):
        raw = json.dumps(body).encode()
        env = {'REQUEST_METHOD': 'POST', 'PATH_INFO': path, 'REMOTE_ADDR': '127.0.0.1',
               'CONTENT_TYPE': 'application/json', 'CONTENT_LENGTH': str(len(raw)),
               'wsgi.input': io.BytesIO(raw), 'HTTP_ORIGIN': origin or app.origin,
               'HTTP_X_REQUESTED_WITH': 'Flashspace'}
        out = {}
        def start(status, headers):
            out['status'] = int(status.split()[0]); out['headers'] = headers
        body_out = app(env, start)
        try:
            out['body'] = json.loads(body_out[0]) if body_out else {}
        except Exception:
            out['body'] = {}
        return out

    def test_extra_origins_trusted_and_unknown_rejected(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            with patch.dict(os.environ, {'APP_EXTRA_ORIGINS': 'https://recrut.teamlens.co , https://other.example'}):
                app = self.build(tmp)
                self.assertIn('https://recrut.teamlens.co', app.origins)
                self.assertIn('https://other.example', app.origins)
                self.assertIn(app.origin, app.origins)
                # POST from the custom domain passes the origin gate (auth then applies, not 403).
                r = self.req(app, '/api/login', {'email': 'x@example.com', 'password': 'wrong-password-long'},
                             origin='https://recrut.teamlens.co')
                self.assertNotEqual(r['status'], 403, r)
                # An untrusted origin is still rejected.
                r = self.req(app, '/api/login', {'email': 'x@example.com', 'password': 'wrong-password-long'},
                             origin='https://evil.example')
                self.assertEqual(r['status'], 403, r)

    def test_default_single_origin_unchanged(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            with patch.dict(os.environ, {'APP_EXTRA_ORIGINS': ''}):
                app = self.build(tmp)
                self.assertEqual(app.origins, {app.origin})


if __name__ == '__main__':
    unittest.main()
