import os
import uuid
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
import test_backend as legacy
from test_v2_server import FakeV2,V2Tests
from backend.v2_endpoint import ConversationalApp
from backend.v2_replay import PlaybackLedger
from backend.server import APIError

class ReplayTests(unittest.TestCase):
    req=legacy.BackendTests.req
    register=legacy.BackendTests.register
    new_v2=V2Tests.new_v2
    def setUp(self):
        import tempfile
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        env=patch.dict(os.environ,{'ADMIN_EMAIL':'','APP_ORIGIN':'http://localhost:8000'})
        env.start();self.addCleanup(env.stop)
        self.ai=FakeV2();self.cu=legacy.FakeClickUp();self.cookie=''
        self.db=self.temp.name+'/replay.db'
        self.app=ConversationalApp(db_path=self.db,roles=[legacy.ROLE],ai=self.ai,clickup=self.cu,start_worker=False)
        with self.app.store.db() as db:db.execute('INSERT INTO settings(key,value) VALUES (?,?)',('v2-bank:growth','sales'))
        self.register();self.f=self.new_v2();self.aid=self.f['application_id'];self.qid=self.f['active']['id']
    def speech(self):return self.req('/api/v2/applications/'+self.aid+'/speech',{'question_id':self.qid})
    def test_initial_plus_two_replays_then_rejected(self):
        for remaining in (2,1,0):
            self.assertEqual(self.speech()['status'],200)
            state=self.req('/api/v2/applications/'+self.aid+'/playback')['body']
            self.assertEqual(state['replays_remaining'],remaining)
        self.assertEqual(self.speech()['status'],429)
        self.assertEqual(self.app.playback.state(self.aid,self.qid)['deliveries'],3)
    def test_restart_does_not_reset_allowance(self):
        for _ in range(3):self.speech()
        self.app=ConversationalApp(db_path=self.db,roles=[legacy.ROLE],ai=self.ai,clickup=self.cu,start_worker=False)
        self.assertEqual(self.speech()['status'],429)
    def test_provider_failure_refunded(self):
        with patch.object(self.ai,'speech',side_effect=APIError(502,'test failure')):
            self.assertEqual(self.speech()['status'],502)
        self.assertEqual(self.app.playback.state(self.aid,self.qid)['deliveries'],0)
        self.assertEqual(self.speech()['status'],200)
    def test_wrong_owner_and_question_do_not_consume(self):
        self.assertEqual(self.req('/api/v2/applications/'+self.aid+'/speech',{'question_id':'other'})['status'],409)
        self.register('other@example.com');self.assertEqual(self.speech()['status'],404)
        self.assertEqual(self.req('/api/v2/applications/'+self.aid+'/playback')['status'],404)
        self.assertEqual(self.app.playback.state(self.aid,self.qid)['deliveries'],0)
    def test_each_question_has_independent_allowance(self):
        for _ in range(3):self.speech()
        f=self.req('/api/v2/applications/'+self.aid+'/answer',{'question_id':self.qid,'version':0,'event_id':'answer-event-1','answer':'A fictional test answer.'})['body']
        self.qid=f['active']['id'];self.assertEqual(self.speech()['status'],200)
        self.assertEqual(self.app.playback.state(self.aid,self.qid)['replays_remaining'],2)
    def test_concurrent_reservations_cannot_exceed_three(self):
        def reserve(_):
            try:self.app.playback.reserve(self.aid,self.qid);return True
            except APIError:return False
        with ThreadPoolExecutor(max_workers=6) as pool:results=list(pool.map(reserve,range(6)))
        self.assertEqual(sum(results),3)
        self.assertEqual(self.app.playback.state(self.aid,self.qid)['deliveries'],3)

@unittest.skipUnless(os.getenv('TEST_POSTGRES_URL'),'Disposable PostgreSQL unavailable')
class ReplayPostgresTests(unittest.TestCase):
    def test_postgres_atomic_cap_and_persistence(self):
        import psycopg
        from test_postgres_integration import schema_test_url
        url=os.environ['TEST_POSTGRES_URL'];schema='fs_replay_'+uuid.uuid4().hex
        with psycopg.connect(url,autocommit=True) as c:c.execute(f'CREATE SCHEMA {schema}')
        try:
            with patch.dict(os.environ,{'DATABASE_URL':schema_test_url(url,schema),'ADMIN_EMAIL':'','RENDER':'','REQUIRE_DATABASE_URL':''}):
                app=ConversationalApp(roles=[legacy.ROLE],ai=FakeV2(),clickup=legacy.FakeClickUp(),start_worker=False)
                with app.store.db() as db:
                    db.execute('INSERT INTO users VALUES (?,?,?,?,0,?)',('u','test@example.com','Test','not-a-login-hash','test'))
                    db.execute('INSERT INTO applications(id,user_id,role_id,data) VALUES (?,?,?,?)',('a','u','growth','{}'))
                def reserve(_):
                    try:app.playback.reserve('a','q');return True
                    except APIError:return False
                with ThreadPoolExecutor(max_workers=6) as pool:results=list(pool.map(reserve,range(6)))
                self.assertEqual(sum(results),3)
                self.assertEqual(PlaybackLedger(app.store).state('a','q')['deliveries_remaining'],0)
        finally:
            with psycopg.connect(url,autocommit=True) as c:c.execute(f'DROP SCHEMA {schema} CASCADE')
