import os
import uuid
import unittest
from unittest.mock import patch
import test_backend as legacy
from test_postgres_integration import schema_test_url
from test_v2_server import FakeV2,V2Tests
from backend.v2_server import InterviewV2App

@unittest.skipUnless(os.getenv('TEST_POSTGRES_URL'),'Disposable PostgreSQL not configured')
class RealV2Tests(unittest.TestCase):
    req=legacy.BackendTests.req
    register=legacy.BackendTests.register
    new_v2=V2Tests.new_v2
    def test_full_v2_session_persists_across_app_recreation(self):
        import psycopg
        url=os.environ['TEST_POSTGRES_URL'];schema='fs_v2_'+uuid.uuid4().hex
        with psycopg.connect(url,autocommit=True) as conn:conn.execute(f'CREATE SCHEMA {schema}')
        try:
            with patch.dict(os.environ,{'DATABASE_URL':schema_test_url(url,schema),'ADMIN_EMAIL':'','REQUIRE_DATABASE_URL':'','RENDER':'','APP_ORIGIN':'http://localhost:8000'}):
                ai=FakeV2();cu=legacy.FakeClickUp()
                self.app=InterviewV2App(roles=[legacy.ROLE],ai=ai,clickup=cu,start_worker=False);self.cookie=''
                with self.app.store.db() as db:db.execute('INSERT INTO settings(key,value) VALUES (?,?)',('v2-bank:growth','operations'))
                self.register();f=self.new_v2();aid=f['application_id']
                for i in range(10):
                    body={'event_id':'pg-event-'+str(i),'version':f['version'],'question_id':f['active']['id'],'answer':'A fictional PostgreSQL test answer.'}
                    response=self.req('/api/v2/applications/'+aid+'/answer',body)
                    self.assertEqual(response['status'],200,response['body']);f=response['body']
                    if i==4:
                        self.app=InterviewV2App(roles=[legacy.ROLE],ai=ai,clickup=cu,start_worker=False)
                        resumed=self.req('/api/v2/applications/'+aid)['body']
                        self.assertEqual(resumed['active'],f['active']);self.assertEqual(resumed['version'],5)
                self.assertEqual(self.app.store.get(aid)['status'],'completed')
                self.assertEqual(len(self.app.flow(aid)['answers']),10)
                self.app.work_once()
                self.assertEqual(len(cu.records[-1]['answers']),10)
                self.assertEqual(self.app.store.get(aid)['sync_status'],'Synced')
        finally:
            with psycopg.connect(url,autocommit=True) as conn:conn.execute(f'DROP SCHEMA {schema} CASCADE')
