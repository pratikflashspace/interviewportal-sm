"""Regression tests for automatic processing and fail-stop supervision."""
import threading
import time
from contextlib import contextmanager
from unittest.mock import patch
import unittest
import test_backend as legacy
from test_durable_backend import DurableBackendTests as BaseTests
from backend.reliable_sync import ReliableSyncApp, Progress, recovery_needed, PHASE_TIMEOUT


class ReliableBackendTests(BaseTests):
    def setUp(self):
        super().setUp()
        self.app = ReliableSyncApp(self.temp.name+'/test.db', [legacy.ROLE], self.ai, self.cu, False)

    def test_post_wakes_after_commit(self):
        self.register()
        self.app.job_wakeup.clear()
        a = self.apply()
        self.assertTrue(self.app.job_wakeup.is_set())
        self.assertEqual(self.app.store.get(a['id'])['status'], 'interview')

    def test_health_requires_admin(self):
        self.assertEqual(self.req('/api/admin/sync-health')['status'], 401)
        self.register()
        self.assertEqual(self.req('/api/admin/sync-health')['status'], 403)
        with self.app.store.db() as db:
            db.execute('UPDATE users SET admin=1')
        result = self.req('/api/admin/sync-health')
        self.assertEqual(result['status'], 200)
        self.assertNotIn('email', result['body'])
        self.assertFalse(result['body']['worker_alive'])

    def test_automatic_worker_drains_without_manual_work_once(self):
        self.register()
        a = self.complete()
        thread = threading.Thread(target=self.app.worker, daemon=True)
        self.app.sync_thread = thread
        thread.start()
        self.app.job_wakeup.set()
        try:
            deadline = time.monotonic()+5
            while time.monotonic()<deadline:
                if self.app.store.get(a['id'])['sync_status']=='Synced':
                    break
                time.sleep(.02)
            self.assertEqual(self.app.store.get(a['id'])['sync_status'], 'Synced')
            self.assertEqual(len(self.cu.records[-1]['answers']), 4)
            self.assertEqual(self.ai.evaluations, 1)
        finally:
            self.app.stop.set()
            self.app.job_wakeup.set()
            thread.join(3)
        self.assertFalse(thread.is_alive())

    def test_busy_lock_does_not_run_duplicate_jobs(self):
        @contextmanager
        def busy():
            self.app.stop.set()
            yield False
        self.app.store.job_lock = busy
        with patch.object(self.app, 'work_once') as work:
            self.app.job_wakeup.set()
            self.app.worker()
        work.assert_not_called()

    def test_failed_cycle_recovers_on_next_iteration(self):
        calls = []
        def work():
            calls.append(1)
            if len(calls)==1:
                raise RuntimeError('private data never logged')
            self.app.stop.set()
        with patch.object(self.app, 'work_once', side_effect=work), patch.object(self.app.stop, 'wait', return_value=False), patch.object(self.app.job_wakeup, 'wait', return_value=True):
            with self.assertLogs('flashspace.sync', level='INFO') as logs:
                self.app.worker()
        self.assertEqual(len(calls), 2)
        self.assertNotIn('private data', '\n'.join(logs.output))


class WatchdogTests(unittest.TestCase):
    def test_dead_and_stuck_threads_require_recovery(self):
        clock = [0]
        progress = Progress(lambda: clock[0])
        self.assertFalse(recovery_needed(progress, True))
        self.assertTrue(recovery_needed(progress, False))
        clock[0] = PHASE_TIMEOUT + 1
        self.assertTrue(recovery_needed(progress, True))
        progress.mark('waiting')
        self.assertFalse(recovery_needed(progress, True))
        self.assertFalse(recovery_needed(progress, False, stopping=True))

    def test_watchdog_exits_instead_of_spawning_another_thread(self):
        from types import SimpleNamespace
        stop = unittest.mock.Mock()
        stop.wait.side_effect = [False, True]
        stop.is_set.return_value = False
        thread = unittest.mock.Mock()
        thread.is_alive.return_value = False
        app = SimpleNamespace(stop=stop, sync_thread=thread, sync_progress=Progress())
        with patch('backend.reliable_sync.os._exit') as exit_process:
            ReliableSyncApp.watchdog(app)
        exit_process.assert_called_once_with(1)
