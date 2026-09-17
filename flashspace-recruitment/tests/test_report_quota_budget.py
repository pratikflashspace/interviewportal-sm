"""Failed report attempts must never exhaust an application's evaluation budget.

Regression: quota used to be charged BEFORE the evaluation call, so a provider
outage or global-quota rejection burned the app's own 20-attempt allowance and
left reports permanently 'pending' for 7 days even after recovery.
"""
import os
import time as _t
import unittest
from unittest.mock import patch

import test_report_retry as harness


class ReportQuotaBudgetTests(harness.ReportRetryTests):
    def test_failed_attempts_do_not_consume_per_app_budget(self):
        aid = self.apply_and_complete()
        with patch.dict(os.environ, {'MAX_AI_CALLS_PER_DAY': '0'}):
            self.app.work_once()  # transcript syncs; report defers on global quota
            with self.app.store.db() as db:
                db.execute('UPDATE pending_reports SET next_retry=0 WHERE application_id=?', (aid,))
            self.app.work_once()  # another failed attempt
        # Restore the global budget and retry: the app's own allowance must be intact.
        self.ai.remaining = 0
        with patch.dict(os.environ, {'MAX_AI_CALLS_PER_DAY': '500'}):
            with self.app.store.db() as db:
                db.execute('UPDATE pending_reports SET next_retry=0 WHERE application_id=?', (aid,))
            self.app.work_once()
        a = self.app.store.get(aid)
        self.assertIsNotNone(a.get('evaluation'),
                             'report must succeed after recovery without burning per-app budget')

    def test_quota_rejections_retry_flat_not_exponential(self):
        aid = self.apply_and_complete()
        with patch.dict(os.environ, {'MAX_AI_CALLS_PER_DAY': '0'}):
            self.app.work_once()
        with self.app.store.db() as db:
            row = db.execute('SELECT failures,next_retry FROM pending_reports WHERE application_id=?', (aid,)).fetchone()
        self.assertEqual(row['failures'], 0)
        self.assertLessEqual(row['next_retry'] - _t.time(), 301,
                             'quota rejections must retry within ~5 minutes, not back off an hour')


if __name__ == '__main__':
    unittest.main()
