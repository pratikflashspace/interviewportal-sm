"""Validate staging-only activation guards without a live database/server."""
import os
import unittest
from unittest.mock import patch,AsyncMock,Mock
from backend import workspace_staging_asgi as runtime

class StagingGuardTests(unittest.TestCase):
    def env(self):
        return {'RENDER_EXTERNAL_URL':runtime.STAGING_ORIGIN,'APP_ORIGIN':runtime.STAGING_ORIGIN,
                'DATABASE_URL':'synthetic-database-reference','TEAMRECRUT_STAGING_SCHEMA_APPROVED':'true'}
    def test_approved_staging_configuration(self):
        with patch.dict(os.environ,self.env(),clear=True):runtime.validate_staging()
    def test_production_or_missing_configuration_rejected(self):
        for key,value in [('RENDER_EXTERNAL_URL','https://interviewportal-sm.onrender.com'),
                          ('APP_ORIGIN','https://other.example'),('DATABASE_URL',''),
                          ('TEAMRECRUT_STAGING_SCHEMA_APPROVED','false')]:
            with self.subTest(key=key):
                env=self.env();env[key]=value
                with patch.dict(os.environ,env,clear=True),self.assertRaises(RuntimeError):runtime.validate_staging()
    def test_missing_acknowledgement_rejected(self):
        env=self.env();del env['TEAMRECRUT_STAGING_SCHEMA_APPROVED']
        with patch.dict(os.environ,env,clear=True),self.assertRaises(RuntimeError):runtime.validate_staging()

class StartupTests(unittest.IsolatedAsyncioTestCase):
    async def test_invalid_runtime_never_constructs_workspace(self):
        with patch.dict(os.environ,{},clear=True),patch.object(runtime,'WorkspaceApp') as constructor:
            with self.assertRaises(RuntimeError):await runtime.startup()
            constructor.assert_not_called()
    async def test_runtime_installs_real_workspace_factory(self):
        previous=runtime.bridge.backend
        try:
            with patch.dict(os.environ,StagingGuardTests().env(),clear=True),patch.object(runtime.asyncio,'to_thread',new_callable=AsyncMock) as thread,patch.object(runtime,'EvidenceOnlyAI',return_value='synthetic-ai'):
                thread.return_value='synthetic-backend'
                await runtime.startup()
                thread.assert_awaited_once_with(runtime.WorkspaceApp,ai='synthetic-ai')
                self.assertEqual(runtime.bridge.backend,'synthetic-backend')
        finally:runtime.bridge.backend=previous
