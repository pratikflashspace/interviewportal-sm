"""Run the existing WSGI contract suite against the opt-in staging app.

Requires the complete repository. These tests are separate from the isolated
turn-logic tests, and must pass before staging deployment or production promotion.
"""
import threading
from concurrent.futures import ThreadPoolExecutor
import test_backend as legacy
from backend.durable_server import DurableInterviewApp


class DurableBackendTests(legacy.BackendTests):
    def setUp(self):
        super().setUp()
        self.app = DurableInterviewApp(self.temp.name + '/test.db', [legacy.ROLE], self.ai, self.cu, False)

    def test_provider_failure_preserves_progress(self):
        self.register()
        a = self.apply()
        self.ai.fail = True
        result = self.req(f"/api/applications/{a['id']}/answer", {
            'turn': 0, 'answer': 'I built an onboarding process.',
        })
        self.assertEqual(result['status'], 200)
        self.assertEqual(len(result['body']['answers']), 1)
        self.assertEqual(result['body']['question_source'], 'standard')
        self.assertTrue(result['body']['question'].startswith('Standard follow-up:'))
        restarted = DurableInterviewApp(self.temp.name + '/test.db', [legacy.ROLE], self.ai, self.cu, False)
        self.assertEqual(len(restarted.store.get(a['id'])['answers']), 1)

    def test_actual_store_commits_before_provider(self):
        self.register()
        a = self.apply()
        original = self.ai.next_question
        def inspect(role, answers):
            saved = self.app.store.get(a['id'])
            self.assertEqual(saved['answers'], answers)
            self.assertEqual(saved['question_source'], 'standard')
            return original(role, answers)
        self.ai.next_question = inspect
        self.assertEqual(self.req(f"/api/applications/{a['id']}/answer", {
            'turn': 0, 'answer': 'I measured the results against the baseline.',
        })['status'], 200)

    def test_parallel_resume_waits_for_final_question(self):
        self.register()
        a = self.apply()
        entered, release, read_started = threading.Event(), threading.Event(), threading.Event()
        def delayed(*args):
            entered.set()
            if not release.wait(5):
                raise RuntimeError('Test timed out')
            return 'What did you learn from the measured outcome?'
        self.ai.next_question = delayed
        def resume():
            read_started.set()
            return self.req('/api/applications')
        with ThreadPoolExecutor(max_workers=2) as pool:
            write = pool.submit(self.req, f"/api/applications/{a['id']}/answer", {
                'turn': 0, 'answer': 'I measured outcomes against the baseline.',
            })
            try:
                self.assertTrue(entered.wait(3))
                read = pool.submit(resume)
                self.assertTrue(read_started.wait(3))
                self.assertFalse(read.done())
            finally:
                release.set()
            self.assertEqual(write.result(timeout=5)['status'], 200)
            result = read.result(timeout=5)
            self.assertEqual(result['status'], 200)
            self.assertEqual(result['body'][0]['question_source'], 'ai')
