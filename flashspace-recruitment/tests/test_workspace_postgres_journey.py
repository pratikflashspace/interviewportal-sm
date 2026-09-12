"""Disposable local CI Postgres only; never uses staging Neon or real accounts."""
import os,tempfile,time,unittest,uuid
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlsplit
from unittest.mock import patch
from backend.workspace_server import WorkspaceApp
from backend.v2_endpoint import EvidenceOnlyAI
from backend.server import APIError
from test_workspace_interview_journey import JourneyTests,Provider,BoundaryClickUp
from test_postgres_integration import schema_test_url
from test_backend import ROLE

@unittest.skipUnless(os.getenv('TEST_POSTGRES_URL'),'Disposable PostgreSQL not configured')
class PostgresJourney(JourneyTests):
    def setUp(self):
        import psycopg
        url=os.environ['TEST_POSTGRES_URL']
        if urlsplit(url).hostname not in ('localhost','127.0.0.1','::1'):raise RuntimeError('Workspace integration only permits a local disposable test database.')
        schema='workspace_ci_'+uuid.uuid4().hex
        with psycopg.connect(url,autocommit=True) as db:db.execute('CREATE SCHEMA '+schema)
        def drop():
            with psycopg.connect(url,autocommit=True) as db:db.execute('DROP SCHEMA '+schema+' CASCADE')
        self.addCleanup(drop)
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        env=patch.dict(os.environ,{'DATABASE_URL':schema_test_url(url,schema),'APP_ORIGIN':'http://localhost:8000','ADMIN_EMAIL':'','RENDER':'','REQUIRE_DATABASE_URL':''})
        env.start();self.addCleanup(env.stop)
        self.clock=time.time();p=patch('time.time',side_effect=lambda:self.clock);p.start();self.addCleanup(p.stop)
        self.provider=Provider();self.ai=object.__new__(EvidenceOnlyAI);self.ai.provider=self.provider
        self.app=self.new_app();self.cookie=''
        self.clickup=BoundaryClickUp(self.app.store);self.app.clickup=self.clickup
        with self.app.store.db() as db:db.execute('INSERT INTO settings VALUES (?,?)',('v2-bank:growth','sales'))
    def new_app(self):return WorkspaceApp(roles=[ROLE],ai=self.ai,start_worker=False,recording_root=self.tmp.name+'/recordings')
    def test_workspace_restart_and_conflicting_profile_writes(self):
        self.signup()
        p=self.ok('/api/workspace/profile')
        self.ok('/api/workspace/profile',{'version':p['version'],'fields':{'summary':'Persisted across restart'}})
        self.app=self.new_app();self.app.clickup=BoundaryClickUp(self.app.store)
        self.assertEqual(self.ok('/api/workspace/profile')['fields']['summary'],'Persisted across restart')
        u=self.app.current_user({'HTTP_COOKIE':self.cookie,'PATH_INFO':'/api/workspace/profile'})
        second=self.new_app()
        def update(app,value):
            try:return app.save_profile(u,{'version':1,'fields':{'summary':value}})['version']
            except APIError as e:return e.status
        with ThreadPoolExecutor(max_workers=2) as pool:
            a=pool.submit(update,self.app,'first writer');b=pool.submit(update,second,'second writer');results=[a.result(),b.result()]
        self.assertEqual(sorted(results),[2,409])
        self.assertIn(self.ok('/api/workspace/profile')['fields']['summary'],('first writer','second writer'))

if __name__=='__main__':unittest.main()
