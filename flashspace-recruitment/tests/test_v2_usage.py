"""Cumulative exhaustion must not prevent v2, but bursts remain bounded."""
import os
import tempfile
import unittest
from unittest.mock import patch
from backend.server import App, Store, APIError
from backend.interview_release import InterviewRelease
from backend.v2_usage import V2UsagePolicy

class UsageTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store=Store(os.path.join(self.tmp.name,'test.sqlite'))
        self.store.init()
        # Exercise the actual release MRO without starting workers/providers.
        self.app=object.__new__(InterviewRelease)
        self.app.store=self.store
        self.a={'id':'synthetic-app','answers':[]}

    def test_historical_limits_do_not_block_any_v2_operation(self):
        with patch('time.time',return_value=1000), patch.dict(os.environ,{'MAX_AI_CALLS_PER_DAY':'1'}):
            App.ai_quota(self.app,self.a,'voice-session-v2',1)
            with self.assertRaises(APIError):App.ai_quota(self.app,self.a,'voice-session-v2',1)
            for kind in ('voice-session-v2','intro-v2','speech-v2','followup-v2','end-check-v2'):
                self.app.ai_quota(self.a,kind,1)
            a={**self.a,'answers':[{'flow_version':2}]}
            self.app.ai_quota(a,'evaluation',1)
        with self.store.db() as db:
            self.assertEqual(db.execute('SELECT n FROM quotas WHERE key=?',('global-ai',)).fetchone()['n'],1)
            self.assertEqual(db.execute('SELECT n FROM quotas WHERE key=?',('synthetic-app:voice-session-v2',)).fetchone()['n'],1)

    def test_more_than_24_reconnections_allowed_across_windows(self):
        for i in range(30):
            with patch('time.time',return_value=1000+i*61):
                self.app.ai_quota(self.a,'voice-session-v2',24)

    def test_application_burst_shared_across_operations_and_expires(self):
        with patch('time.time',return_value=1000):
            for i in range(20):self.app.ai_quota(self.a,'voice-session-v2' if i%2 else 'intro-v2',5)
            with self.assertRaises(APIError) as caught:self.app.ai_quota(self.a,'speech-v2',42)
            self.assertEqual(caught.exception.status,429)
        with patch('time.time',return_value=1061):self.app.ai_quota(self.a,'voice-session-v2',24)

    def test_global_burst_shared_between_applications(self):
        with patch('time.time',return_value=1000):
            for i in range(120):self.app.ai_quota({'id':str(i)},'voice-session-v2',24)
            with self.assertRaises(APIError):self.app.ai_quota({'id':'next'},'voice-session-v2',24)
        with patch('time.time',return_value=1061):self.app.ai_quota({'id':'next'},'voice-session-v2',24)

    def test_v1_policy_unchanged(self):
        with patch.dict(os.environ,{'MAX_AI_CALLS_PER_DAY':'1'}):
            self.app.ai_quota(self.a,'speech',16)
            with self.assertRaises(APIError):self.app.ai_quota(self.a,'speech',16)

    def test_v1_evaluation_still_delegates(self):
        with patch.object(App,'ai_quota',return_value=None) as original:
            self.app.ai_quota({'id':'old','answers':[{'answer':'legacy'}]},'evaluation',20)
            original.assert_called_once()

    def test_database_error_not_swallowed(self):
        with patch.object(self.store,'quota',side_effect=RuntimeError('test database failure')):
            with self.assertRaises(RuntimeError):self.app.ai_quota(self.a,'voice-session-v2',24)

    def test_policy_uses_existing_atomic_store_with_short_windows(self):
        with patch.object(self.store,'quota') as quota:
            self.app.ai_quota(self.a,'voice-session-v2',24)
        self.assertEqual([c.args for c in quota.call_args_list],[('v2-burst:application:synthetic-app',20,60),('v2-burst:global',120,60)])
        self.assertIs(InterviewRelease.ai_quota,V2UsagePolicy.ai_quota)
