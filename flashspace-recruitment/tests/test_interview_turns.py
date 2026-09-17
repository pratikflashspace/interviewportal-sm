"""Dependency-free turn logic tests. Not a substitute for Postgres/WSGI tests."""
import json
import sqlite3
import tempfile
import unittest
from types import SimpleNamespace
from backend.interview_turns import save_answer


class Error(Exception):
    def __init__(self, status, message):
        self.status = status
        super().__init__(message)


def text(body, key, lo, hi):
    value = body.get(key)
    if not isinstance(value, str) or not lo <= len(value.strip()) <= hi:
        raise Error(400, 'Invalid answer')
    return value.strip()


class Store:
    def __init__(self, path):
        self.path = path
        self.saves = 0
        self.fail_save = None
        with sqlite3.connect(path) as db:
            db.execute('CREATE TABLE IF NOT EXISTS records(id TEXT PRIMARY KEY, data TEXT NOT NULL)')

    def get(self, identifier):
        with sqlite3.connect(self.path) as db:
            row = db.execute('SELECT data FROM records WHERE id=?', (identifier,)).fetchone()
        if not row:
            raise Error(404, 'Not found')
        return json.loads(row[0])

    def save(self, a):
        self.saves += 1
        if self.saves == self.fail_save:
            raise RuntimeError('Simulated database failure')
        with sqlite3.connect(self.path) as db:
            db.execute('INSERT INTO records VALUES (?,?) ON CONFLICT(id) DO UPDATE SET data=excluded.data',
                       (a['id'], json.dumps(a)))
        return self.get(a['id'])


class TurnTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = Store(self.temp.name + '/turns.db')
        self.store.save({'id': 'a', 'user_id': 'owner', 'status': 'interview', 'answers': [],
                         'question': 'Describe a relevant project.',
                         'role_snapshot': {'title': 'Generalist (Sales)'}})
        self.calls = 0
        self.fail_ai = False
        self.fail_quota = False
        self.app = SimpleNamespace(store=self.store, ai=SimpleNamespace(next_question=self.next_question),
                                   ai_quota=self.quota)

    def tearDown(self):
        self.temp.cleanup()

    def quota(self, *args):
        if self.fail_quota:
            raise Error(429, 'Quota exceeded')

    def next_question(self, role, answers):
        self.calls += 1
        committed = Store(self.store.path).get('a')
        self.assertEqual(committed['answers'], answers)
        self.assertEqual(committed['question_source'], 'standard')
        if self.fail_ai:
            raise Error(502, 'Do not persist this provider detail')
        return 'How did you measure the outcome of that project?'

    def submit(self, turn=0, answer='I improved lead qualification with a checklist.', user='owner'):
        return save_answer(self.app, 'a', user, {'turn': turn, 'answer': answer},
                           Error, text, lambda: '2026-09-09T00:00:00Z')

    def test_answer_committed_before_inference(self):
        a = self.submit()
        self.assertEqual(len(a['answers']), 1)
        self.assertEqual(a['question_source'], 'ai')

    def test_provider_failure_and_restart_keep_answer_and_question(self):
        self.fail_ai = True
        self.submit()
        a = Store(self.store.path).get('a')
        self.assertEqual(len(a['answers']), 1)
        self.assertTrue(a['question'].startswith('Standard follow-up:'))
        self.assertNotIn('provider detail', json.dumps(a))

    def test_retry_is_idempotent_and_free(self):
        original = self.submit()
        retried = self.submit()
        self.assertEqual(original, retried)
        self.assertEqual(self.calls, 1)

    def test_failed_provider_retry_does_not_duplicate_answer(self):
        self.fail_ai = True
        original = self.submit()
        self.assertEqual(self.submit(), original)
        self.assertEqual(self.calls, 1)

    def test_quota_failure_keeps_committed_standard_question(self):
        self.fail_quota = True
        a = self.submit()
        self.assertEqual(a['question_source'], 'standard')
        self.assertEqual(len(a['answers']), 1)
        self.assertEqual(self.calls, 0)

    def test_database_failure_prevents_provider_call(self):
        self.store.fail_save = 2
        with self.assertRaises(RuntimeError):
            self.submit()
        self.assertEqual(self.calls, 0)
        self.assertEqual(self.store.get('a')['answers'], [])

    def test_second_database_failure_preserves_first_commit(self):
        self.store.fail_save = 3
        with self.assertRaises(RuntimeError):
            self.submit()
        a = self.store.get('a')
        self.assertEqual(len(a['answers']), 1)
        self.assertEqual(a['question_source'], 'standard')
        self.assertEqual(self.submit(), a)

    def test_process_exit_during_inference_preserves_answer(self):
        def crash(*args):
            raise SystemExit()
        self.app.ai.next_question = crash
        with self.assertRaises(SystemExit):
            self.submit()
        self.assertEqual(len(Store(self.store.path).get('a')['answers']), 1)

    def test_other_candidate_cannot_read_or_write(self):
        with self.assertRaises(Error) as caught:
            self.submit(user='other')
        self.assertEqual(caught.exception.status, 404)
        self.assertEqual(self.store.get('a')['answers'], [])

    def test_conflicting_retry_rejected(self):
        self.submit()
        with self.assertRaises(Error) as caught:
            self.submit(answer='This is a different answer to the same turn.')
        self.assertEqual(caught.exception.status, 409)

    def test_invalid_turn_and_short_answer_rejected(self):
        for turn, answer in [(True, 'A sufficiently long answer.'), (2, 'A sufficiently long answer.'),
                             (-1, 'A sufficiently long answer.'), (0, 'short')]:
            with self.assertRaises(Error):
                self.submit(turn, answer)
        self.assertEqual(self.calls, 0)

    def test_fourth_answer_does_not_call_ai_and_is_retryable(self):
        for i in range(4):
            a = self.submit(i, f'I measured outcome number {i} using clear goals.')
        self.assertEqual(self.calls, 3)
        self.assertIsNone(a['question'])
        self.assertEqual(a['question_source'], 'complete')
        a['status'] = 'completed'
        self.store.save(a)
        self.assertEqual(len(self.submit(3, 'I measured outcome number 3 using clear goals.')['answers']), 4)

    def test_invalid_generated_question_uses_standard(self):
        self.app.ai.next_question = lambda *args: None
        self.assertEqual(self.submit()['question_source'], 'standard')


if __name__ == '__main__':
    unittest.main()
