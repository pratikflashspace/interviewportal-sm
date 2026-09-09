"""Offline adapter/configuration tests. External calls are mocked, not live probes."""
import base64,io,json,os,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError
from backend.server import AI,APIError,Store,App
from backend.cloudflare_provider import CloudflareProvider,STT_MODEL,TTS_MODEL
from backend.postgres_store import Connection,validate_url,select_store,make_store,DDL

class Response:
    def __init__(self,body,mime='application/json'):self.body=body;self.headers={'Content-Type':mime}
    def read(self,limit):return self.body[:limit]
    def __enter__(self):return self
    def __exit__(self,*args):pass

class CloudflareTests(unittest.TestCase):
    def setUp(self):
        self.p=patch.dict(os.environ,{'CLOUDFLARE_ACCOUNT_ID':'0'*32,'CLOUDFLARE_GATEWAY_ID':'test-gateway','CLOUDFLARE_API_TOKEN':'test-token-not-a-secret','CLOUDFLARE_LLM_MODEL':'@cf/meta/llama-3.1-8b-instruct-fast'},clear=False);self.p.start();self.provider=CloudflareProvider(APIError)
    def tearDown(self):self.p.stop()
    def mock(self,result):return patch('backend.cloudflare_provider.request.urlopen',return_value=Response(json.dumps({'success':True,'result':result}).encode()))
    def test_stt_uses_supported_batch_api_and_gateway_header(self):
        with self.mock({'text':' A useful answer. '}) as send:
            self.assertEqual(self.provider.transcribe(b'wav-data','audio/wav')['text'],'A useful answer.')
        req=send.call_args.args[0];self.assertTrue(req.full_url.endswith('/ai/run/'+STT_MODEL));self.assertEqual(req.get_header('Cf-aig-gateway-id'),'test-gateway');self.assertEqual(req.get_header('Cf-aig-skip-cache'),'true');self.assertEqual(req.get_header('Cf-aig-collect-log'),'false');self.assertEqual(base64.b64decode(json.loads(req.data)['audio']),b'wav-data')
    def test_tts_uses_aura_text_speaker_and_mp3(self):
        with patch('backend.cloudflare_provider.request.urlopen',return_value=Response(b'ID3mock','audio/mpeg')) as send:
            self.assertEqual(self.provider.speech('Tell me about your project.'),b'ID3mock')
        req=send.call_args.args[0];self.assertTrue(req.full_url.endswith('/ai/run/'+TTS_MODEL));self.assertEqual(json.loads(req.data)['encoding'],'mp3');self.assertIn('text',json.loads(req.data))
    def test_tts_base64_envelope(self):
        with self.mock({'audio':base64.b64encode(b'ID3mock').decode()}):self.assertEqual(self.provider.speech('hello'),b'ID3mock')
    def test_invalid_tts_fails(self):
        with self.mock({'audio':'not_base64!'}):
            with self.assertRaises(APIError):self.provider.speech('hello')
    def test_invalid_audio_format_fails_before_network(self):
        with self.assertRaises(APIError):self.provider.transcribe(b'data','text/plain')
    def test_empty_transcription_fails(self):
        with self.mock({'text':'   '}):
            with self.assertRaises(APIError):self.provider.transcribe(b'data','audio/webm')
    def test_structured_object_and_fenced_json(self):
        for response in ({'question':'What did you learn?'},'```json\n{"question":"What did you learn?"}\n```'):
            with self.mock({'response':response}):self.assertEqual(self.provider.structured('system',{},'q',{})['question'],'What did you learn?')
    def test_invalid_json_never_saved(self):
        with self.mock({'response':'not JSON'}):
            with self.assertRaises(APIError):self.provider.structured('system',{},'q',{})
    def test_failed_envelope_is_not_success(self):
        with patch('backend.cloudflare_provider.request.urlopen',return_value=Response(b'{"success":false,"errors":[{"message":"sensitive"}]}')):
            with self.assertRaises(APIError) as err:self.provider.structured('s',{},'q',{})
        self.assertNotIn('sensitive',err.exception.message)
    def test_permission_error_does_not_leak_token(self):
        exc=HTTPError('https://api.cloudflare.com',403,'Denied',{},None)
        with patch('backend.cloudflare_provider.request.urlopen',side_effect=exc):
            with self.assertRaises(APIError) as err:self.provider.speech('hello')
        self.assertIn('access denied',err.exception.message);self.assertNotIn('test-token',err.exception.message)
    def test_missing_token_fails_closed(self):
        self.provider.token=''
        with self.assertRaises(APIError):self.provider.speech('hello')
    def test_invalid_model_cannot_redirect_credentials(self):
        with self.assertRaises(APIError):self.provider.run('https://evil.example',{})
    def test_ai_pipeline_scores_report_with_actual_model(self):
        criteria=[{'name':n,'score':3,'reason':'Concrete statement.','evidence':'I measured impact.'} for n in ['Relevant experience','Problem solving','Evidence of impact']]
        with self.mock({'response':{'summary':'Unverified impact claim.','criteria':criteria}}):
            r=AI().evaluate({'title':'Growth','details':'Build partnerships.'},[{'question':'What changed?','answer':'I measured impact.'}])
        self.assertEqual(r['score'],60);self.assertEqual(r['model'],self.provider.model);self.assertTrue(r['human_review_required'])

class PostgresConfigTests(unittest.TestCase):
    def test_remote_database_requires_tls(self):
        for url in ('sqlite:///data.db','postgresql://u:p@host/db','postgresql://u:p@host/db?sslmode=disable'):
            with self.assertRaises(RuntimeError):validate_url(url)
        self.assertTrue(validate_url('postgresql://u:p@host/db?sslmode=require'))
    def test_local_pg_allowed_without_ssl(self):self.assertTrue(validate_url('postgresql://u:p@localhost/db'))
    def test_render_never_falls_back_to_ephemeral_sqlite(self):
        with patch.dict(os.environ,{'DATABASE_URL':'','RENDER':'true'}):
            with self.assertRaises(RuntimeError):select_store(Store,APIError)
    def test_explicit_test_database_does_not_touch_production(self):
        with tempfile.TemporaryDirectory() as d,patch.dict(os.environ,{'DATABASE_URL':'postgresql://u:p@production/db?sslmode=require','RENDER':'true'}):
            store=select_store(Store,APIError,d+'/test.sqlite3');self.assertIsInstance(store,Store);store.init()
    def test_query_parameters_remain_separate(self):
        class Driver:
            def execute(self,sql,params):self.sql,self.params=sql,params;return 'cursor'
        driver=Driver();db=Connection(driver);param="';DROP TABLE users;--"
        self.assertEqual(db.execute("SELECT id FROM applications WHERE user_id=? ORDER BY data->>'created_at' DESC",(param,)),'cursor');self.assertNotIn(param,driver.sql);self.assertIn('%s',driver.sql);self.assertIn('data::jsonb',driver.sql);self.assertEqual(driver.params,(param,))
    def test_schema_uses_postgres_types_and_idempotent_ddl(self):
        self.assertTrue(all('IF NOT EXISTS' in s for s in DDL));self.assertTrue(any('DOUBLE PRECISION' in s for s in DDL));self.assertFalse(any('PRAGMA' in s or 'DROP ' in s for s in DDL))
    def test_atomic_pg_quota_sql(self):
        class FakeBase:pass
        cls=make_store(FakeBase,APIError);obj=object.__new__(cls)
        class Context:
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def execute(self,sql,args):self.sql,self.args=sql,args;return self
            def fetchone(self):return {'n':1}
        context=Context();obj.db=lambda:context;obj.quota('test',10);self.assertIn('RETURNING n',context.sql);self.assertIn('quotas.n<?',context.sql)
    def test_runtime_health_does_not_wake_database(self):
        with tempfile.TemporaryDirectory() as d,patch.dict(os.environ,{'ADMIN_EMAIL':'','REQUIRE_DATABASE_URL':'','RENDER':''}):
            app=App(db_path=d+'/test.sqlite3',roles=[],start_worker=False)
            with patch.object(app.store,'db',side_effect=AssertionError('must not connect')):
                self.assertTrue(app.route({'PATH_INFO':'/api/health','REQUEST_METHOD':'GET'}, {})[0]['ok'])

if __name__=='__main__':unittest.main()
