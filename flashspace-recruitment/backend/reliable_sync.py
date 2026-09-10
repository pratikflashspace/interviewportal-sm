"""Opt-in supervised sync worker. One worker process remains required.

A hung thread is never replaced in-process: the process exits so Gunicorn can
restart it and close all its database connections before normal job recovery.
"""
import logging
import os
import threading
import time
from contextlib import contextmanager
from .durable_server import DurableInterviewApp
from .server import APIError

LOG = logging.getLogger('flashspace.sync')
POLL_SECONDS = 30
PHASE_TIMEOUT = 180


class Progress:
    def __init__(self, clock=time.monotonic):
        self.clock = clock
        self.lock = threading.Lock()
        self.phase = 'starting'
        self.since = clock()
        self.sequence = 0

    def mark(self, phase):
        with self.lock:
            self.phase, self.since = phase, self.clock()
            self.sequence += 1

    def snapshot(self):
        with self.lock:
            return {'phase': self.phase, 'age_seconds': max(0, int(self.clock() - self.since)),
                    'sequence': self.sequence}


def recovery_needed(progress, alive, stopping=False):
    if stopping:
        return False
    return not alive or progress.snapshot()['age_seconds'] > PHASE_TIMEOUT


class ReliableSyncApp(DurableInterviewApp):
    def __init__(self, db_path=None, roles=None, ai=None, clickup=None, start_worker=True):
        self.sync_progress = Progress()
        self.sync_thread = None
        # Never start the inherited untracked thread as well.
        super().__init__(db_path, roles, ai, clickup, False)
        if start_worker:
            self.sync_thread = threading.Thread(target=self.worker, name='sync-worker', daemon=True)
            self.sync_thread.start()
            threading.Thread(target=self.watchdog, name='sync-watchdog', daemon=True).start()
            self.job_wakeup.set()

    @contextmanager
    def phase(self, name):
        self.sync_progress.mark(name)
        LOG.info('sync_phase phase=%s', name)
        started = time.monotonic()
        try:
            yield
        finally:
            LOG.info('sync_phase_finished phase=%s elapsed_seconds=%d', name, time.monotonic()-started)

    def watchdog(self):
        while not self.stop.wait(5):
            if recovery_needed(self.sync_progress, self.sync_thread.is_alive(), self.stop.is_set()):
                state = self.sync_progress.snapshot()
                LOG.error('sync_worker_stalled phase=%s age_seconds=%d action=exit_for_supervisor',
                          state['phase'], state['age_seconds'])
                # Do not spawn a duplicate worker while an old call/lock is live.
                # No credentials, application identifiers or responses in logs.
                os._exit(1)

    def worker(self):
        LOG.info('sync_worker_started')
        while not self.stop.is_set():
            self.sync_progress.mark('waiting')
            self.job_wakeup.wait(POLL_SECONDS)
            self.job_wakeup.clear()
            if self.stop.is_set():
                break
            if time.monotonic() - self.last_http_activity > 600:
                # Idle is healthy. Do not keep Neon awake with empty polls.
                continue
            try:
                if hasattr(self.store, 'job_lock'):
                    with self.phase('job_lock'):
                        with self.store.job_lock() as acquired:
                            if acquired:
                                self.work_once()
                            else:
                                LOG.info('sync_lock_busy')
                            # Watch commit/release separately from the last job.
                            self.sync_progress.mark('job_lock_release')
                else:
                    self.work_once()
            except Exception:
                LOG.error('sync_cycle_failed phase=%s', self.sync_progress.snapshot()['phase'])
                # Avoid a tight retry loop when HTTP traffic keeps waking us.
                self.stop.wait(5)
        self.sync_progress.mark('stopped')

    def work_once(self):
        with self.phase('queue_read'):
            with self.store.db() as db:
                ids = [r['id'] for r in db.execute(
                    'SELECT id FROM applications WHERE synced_version<version AND next_retry<=? ORDER BY next_retry LIMIT 8',
                    (time.time(),))]
        LOG.info('sync_batch pending_count=%d', len(ids))
        for aid in ids:
            if self.stop.is_set():
                break
            try:
                evaluation_error = None
                with self.phase('application_lock'):
                    with self.lock:
                        with self.phase('application_read'):
                            a = self.store.get(aid)
                        if a['status'] == 'completed' and not a.get('evaluation'):
                            try:
                                with self.phase('evaluation_quota'):
                                    self.ai_quota(a, 'evaluation', 20)
                                with self.phase('evaluation'):
                                    a['evaluation'] = self.ai.evaluate(a['role_snapshot'], a['answers'])
                                with self.phase('report_save'):
                                    a = self.store.save(a)
                            except Exception as exc:
                                evaluation_error = exc
                                LOG.warning('sync_evaluation_failed status=%d', exc.status if isinstance(exc, APIError) else 500)
                        version = a['version']
                with self.phase('clickup_sync'):
                    self.clickup.sync(a)
                # Even when evaluation failed, the transcript above was synced.
                if evaluation_error:
                    raise evaluation_error
                with self.phase('sync_acknowledge'):
                    with self.store.db() as db:
                        db.execute('UPDATE applications SET synced_version=?,failures=0,sync_error=NULL,next_retry=0 WHERE id=?', (version, aid))
                LOG.info('sync_job_completed')
            except Exception as exc:
                message = exc.message if isinstance(exc, APIError) else 'Integration error. Check server configuration.'
                with self.phase('retry_save'):
                    with self.store.db() as db:
                        row = db.execute('SELECT failures FROM applications WHERE id=?', (aid,)).fetchone()
                        if row is None:
                            continue
                        failures = row['failures'] + 1
                        db.execute('UPDATE applications SET failures=?,next_retry=?,sync_error=? WHERE id=?',
                                   (failures, time.time()+min(900,15*(2**min(failures,6))), message, aid))
                LOG.warning('sync_job_retry status=%d', exc.status if isinstance(exc, APIError) else 500)

    def route(self, env, body):
        if env.get('PATH_INFO') == '/api/admin/sync-health' and env.get('REQUEST_METHOD') == 'GET':
            user = self.current_user(env)
            if not user['admin']:
                raise APIError(403, 'Recruiter access is required.')
            return {**self.sync_progress.snapshot(),
                    'worker_alive': bool(self.sync_thread and self.sync_thread.is_alive()),
                    'phase_timeout_seconds': PHASE_TIMEOUT}, []
        return super().route(env, body)

    def __call__(self, env, start_response):
        try:
            return super().__call__(env, start_response)
        finally:
            # Wake AFTER commits as well as on request entry. An early wake can
            # otherwise scan before the submitted answer/finish/retry is saved.
            if env.get('REQUEST_METHOD') == 'POST' and env.get('PATH_INFO', '').startswith('/api/'):
                self.job_wakeup.set()


def create_app():
    from .sarvam_server import SarvamAI
    return ReliableSyncApp(ai=SarvamAI())
