import os
import unittest
from unittest.mock import patch
import test_backend as legacy
from test_durable_backend import DurableBackendTests
from backend.v2_server import InterviewV2App,InterviewV2AI,V2ClickUp,CONSENT
from backend.v2_endpoint import ConversationalApp

class FakeV2(legacy.FakeAI):
    def followup(self,*args):return None

class V2Tests(DurableBackendTests):
    def setUp(self):
        super().setUp();self.ai=FakeV2()
        self.app=InterviewV2App(self.temp.name+'/test.db',[legacy.ROLE],self.ai,self.cu,False)
        with self.app.store.db() as db:db.execute('INSERT INTO settings(key,value) VALUES (?,?)',('v2-bank:growth','sales'))
    def new_v2(self):
        response=self.req('/api/v2/applications',{'role_id':'growth','experience':'A fictional project for testing.','consent':True,'consent_version':CONSENT})
        self.assertEqual(response['status'],200,response['body']);return response['body']
    def test_v2_complete_without_four_answer_limit(self):
        self.register();f=self.new_v2();aid=f['application_id']
        for i in range(10):
            response=self.req('/api/v2/applications/'+aid+'/answer',{'event_id':'test-event-'+str(i),'version':f['version'],'question_id':f['active']['id'],'answer':'A fictional answer.'})
            self.assertEqual(response['status'],200,response['body']);f=response['body']
            if i==3:self.assertEqual(f['status'],'interview')
        saved=self.app.store.get(aid)
        self.assertEqual(saved['status'],'completed');self.assertEqual(len(saved['answers']),10)
        self.assertEqual(saved['consent_version'],CONSENT)
        self.assertEqual(self.req('/api/applications/'+aid+'/finish',{})['status'],409)
    def test_no_conversion_of_existing_v1_application(self):
        self.register();a=self.apply()
        response=self.req('/api/v2/applications',{'role_id':'growth','experience':'A fictional project for testing.','consent':True,'consent_version':CONSENT})
        self.assertEqual(response['status'],409);self.assertIsNone(self.app.flow(a['id']))
    def test_explicit_consent_and_mapping_required(self):
        self.register()
        self.assertEqual(self.req('/api/v2/applications',{'role_id':'growth','experience':'Fictional test application.','consent':True})['status'],400)
        with self.app.store.db() as db:db.execute('DELETE FROM settings WHERE key=?',('v2-bank:growth',))
        self.assertEqual(self.req('/api/v2/applications',{'role_id':'growth','experience':'Fictional test application.','consent':True,'consent_version':CONSENT})['status'],409)
    def test_bank_mapping_requires_admin(self):
        self.register();self.assertEqual(self.req('/api/admin/v2-banks')['status'],403)
        self.assertEqual(self.req('/api/admin/v2-banks',{'role_id':'growth','bank':'marketing'})['status'],403)
    def test_v2_ownership_and_resume(self):
        self.register();f=self.new_v2();cookie=self.cookie
        self.register('other@example.com')
        self.assertEqual(self.req('/api/v2/applications/'+f['application_id'])['status'],404)
        self.cookie=cookie
        self.assertEqual(self.req('/api/v2/applications/'+f['application_id'])['body']['active'],f['active'])
    def test_answer_saved_before_ai_and_replay(self):
        self.register();f=self.new_v2();aid=f['application_id'];seen=[]
        def fail(*args):
            seen.append(len(self.app.store.get(aid)['answers']))
            raise RuntimeError('provider unavailable')
        self.ai.followup=fail
        body={'event_id':'same-event','version':0,'question_id':f['active']['id'],'answer':'A fictional answer.'}
        first=self.req('/api/v2/applications/'+aid+'/answer',body);second=self.req('/api/v2/applications/'+aid+'/answer',body)
        self.assertEqual(first['status'],200);self.assertEqual(second['status'],200)
        self.assertEqual(seen,[1]);self.assertEqual(len(self.app.store.get(aid)['answers']),1)
    def test_unpublished_roles(self):
        self.app.role_repository.update('growth',{'version':1,'state':'draft'},'test-admin',True)
        self.assertEqual(self.req('/api/roles')['body'],[])
    def test_atomic_flow_mirror_rolls_back_on_failure(self):
        from contextlib import contextmanager
        from backend.v2_flow import commit_answer
        self.register();f=self.new_v2();aid=f['application_id'];a=self.app.store.get(aid)
        pending,_=commit_answer(self.app.flow(aid),'rollback-event',0,f['active']['id'],'A test answer.','test')
        original=self.app.store.db
        class FailUpdate:
            def __init__(self,db):self.db=db
            def execute(self,sql,params=()):
                if sql.startswith('UPDATE applications SET data='):raise RuntimeError('simulated write failure')
                return self.db.execute(sql,params)
        @contextmanager
        def broken():
            with original() as db:yield FailUpdate(db)
        with patch.object(self.app.store,'db',broken):
            with self.assertRaises(RuntimeError):self.app.save_flow(a,pending)
        self.assertEqual(self.app.flow(aid)['version'],0)
        self.assertEqual(self.app.store.get(aid)['answers'],[])

class StreamContractTests(unittest.TestCase):
    def test_strip_provider_metadata_and_reject_invalid_event(self):
        from backend.v2_stream import clean_event
        self.assertEqual(clean_event({'event':'transcript.final','utterance_idx':0,'text':'Hello','private':'hidden'}),{'event':'transcript.final','utterance_idx':0,'text':'Hello'})
        for e in ({'event':'error'}, {'event':'vad.speech_start','utterance_idx':True}, {'event':'transcript.final','utterance_idx':0,'text':'x'*6001}):self.assertIsNone(clean_event(e))

class JavascriptTurnTests(unittest.TestCase):
    def test_node_turn_arbitration(self):
        import shutil,subprocess
        from pathlib import Path
        if not shutil.which('node'):self.skipTest('Node unavailable')
        file=Path(__file__).resolve().parents[1]/'web/src/v2/turn-controller.test.mjs'
        result=subprocess.run(['node','--test',str(file)],capture_output=True,text=True,timeout=20)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)

class StreamAuthTests(unittest.IsolatedAsyncioTestCase):
    async def test_reject_wrong_origin_without_upstream(self):
        from types import SimpleNamespace
        from unittest.mock import AsyncMock
        import backend.v2_stream as bridge
        socket=SimpleNamespace(path_params={'aid':'test'},headers={'origin':'https://evil.example'},close=AsyncMock())
        with patch.object(bridge,'backend',SimpleNamespace(origin='https://site.example')),patch.object(bridge,'connect') as upstream:
            await bridge.voice(socket)
        upstream.assert_not_called();socket.close.assert_awaited_once_with(code=1008)
    async def test_reject_invalid_cookie_without_upstream(self):
        from types import SimpleNamespace
        from unittest.mock import AsyncMock,Mock
        import backend.v2_stream as bridge
        socket=SimpleNamespace(path_params={'aid':'test'},headers={'origin':'https://site.example'},close=AsyncMock())
        backend=SimpleNamespace(origin='https://site.example',current_user=Mock(side_effect=ValueError()))
        with patch.object(bridge,'backend',backend),patch.object(bridge,'connect') as upstream:
            await bridge.voice(socket)
        upstream.assert_not_called();socket.close.assert_awaited_once_with(code=1008)
