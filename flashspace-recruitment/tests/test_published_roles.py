"""Confirmed public vacancy contract; no live database or provider calls."""
import copy
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from backend.server import App

ROOT = Path(__file__).resolve().parents[1]
EXPECTED = {
    'generalist-sales': 'Generalist (Sales)',
    'generalist-operations': 'Generalist (Operations)',
    'ai-marketing': 'AI Marketing',
}

class PublishedRoleTests(unittest.TestCase):
    def setUp(self):
        self.roles = json.loads((ROOT / 'roles.json').read_text())

    def test_exact_confirmed_vacancies_and_terms(self):
        self.assertEqual(len(self.roles), 3)
        self.assertEqual({r['id']: r['title'] for r in self.roles}, EXPECTED)
        for role in self.roles:
            with self.subTest(role=role['id']):
                self.assertIs(role['published'], True)
                self.assertEqual(role['location'], 'Remote / On-site — both available')
                self.assertEqual(role['type'], 'Full-time')
                self.assertEqual(role['experience'], '0-2 years experience')
                for field in ('department', 'description', 'details'):
                    self.assertTrue(role[field].strip())
                self.assertTrue(role['skills'])

    def test_marketing_owns_full_vertical_and_channels(self):
        role = next(r for r in self.roles if r['id'] == 'ai-marketing')
        content = (role['description'] + ' ' + role['details']).lower()
        for phrase in ('entire marketing vertical', 'end-to-end ownership', 'paid ads', 'organic reach', 'social media', 'ai tools', 'measure results'):
            self.assertIn(phrase, content)

    def test_public_endpoint_publishes_confirmed_roles_without_flag(self):
        # The public roles route needs only self.roles; no DB or external service.
        app = object.__new__(App)
        app.roles = self.roles
        result, _ = app.route({'PATH_INFO': '/api/roles', 'REQUEST_METHOD': 'GET'}, {})
        self.assertEqual({r['id']: r['title'] for r in result}, EXPECTED)
        self.assertTrue(all('published' not in r for r in result))
        for configured, public in zip(self.roles, result):
            self.assertEqual(public, {k: v for k, v in configured.items() if k != 'published'})
        app.roles = copy.deepcopy(self.roles)
        app.roles[0]['published'] = False
        result, _ = app.route({'PATH_INFO': '/api/roles', 'REQUEST_METHOD': 'GET'}, {})
        self.assertEqual(len(result), 2)
        self.assertNotIn('generalist-sales', {r['id'] for r in result})

    def test_configuration_passes_actual_startup_validation(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {'ADMIN_EMAIL': '', 'REQUIRE_DATABASE_URL': '', 'RENDER': ''}):
            app = App(db_path=str(Path(directory) / 'roles-test.sqlite3'), roles=self.roles, start_worker=False)
            self.assertEqual(app.roles, self.roles)

if __name__ == '__main__':
    unittest.main()
