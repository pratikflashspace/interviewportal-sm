"""Optional real Postgres integration. Set TEST_POSTGRES_URL to a TEST database.
Creates a unique schema, tests against it and drops only that schema afterwards.
Never set this variable to a production database in Render's build settings.
"""
import io,json,os,unittest,uuid
from urllib.parse import urlsplit,urlunsplit,parse_qsl,urlencode
from unittest.mock import patch
from backend.server import App

@unittest.skipUnless(os.getenv('TEST_POSTGRES_URL'),'No disposable Postgres test connection configured')
class RealPostgresTest(unittest.TestCase):
    def test_login_application_and_restart_persistence(self):
        import psycopg
        url=os.environ['TEST_POSTGRES_URL'];schema='fs_test_'+uuid.uuid4().hex
        with psycopg.connect(url,autocommit=True) as conn:conn.execute(f'CREATE SCHEMA {schema}')
        try:
            p=urlsplit(url);q=dict(parse_qsl(p.query));q['options']='-c search_path='+schema
            scoped=urlunsplit((p.scheme,p.netloc,p.path,urlencode(q),p.fragment))
            with patch.dict(os.environ,{'DATABASE_URL':scoped,'ADMIN_EMAIL':'','REQUIRE_DATABASE_URL':'','RENDER':''}):
                role={'id':'test','title':'Test role','department':'Test','location':'Remote','type':'Full-time','experience':'Any','description':'Test description','details':'Test requirements','skills':['Testing'],'published':True}
                class AI:
                    def next_question(self,r,answers):return 'How did you measure the impact?'
                app=App(roles=[role],ai=AI(),start_worker=False);cookie=''
                def req(path,body):
                    nonlocal cookie
                    data=json.dumps(body).encode();result={}
                    def start(status,headers):result['status']=int(status.split()[0]);result['headers']=dict(headers)
                    raw=b''.join(app({'REQUEST_METHOD':'POST','PATH_INFO':path,'HTTP_COOKIE':cookie,'HTTP_ORIGIN':app.origin,'HTTP_X_REQUESTED_WITH':'Flashspace','CONTENT_TYPE':'application/json','CONTENT_LENGTH':str(len(data)),'wsgi.input':io.BytesIO(data)},start))
                    if result['headers'].get('Set-Cookie'):cookie=result['headers']['Set-Cookie'].split(';')[0]
                    self.assertEqual(result['status'],200,raw.decode());return json.loads(raw)
                req('/api/register',{'email':'test@example.com','name':'Test Candidate','password':'OnlyForTest123!'})
                a=req('/api/applications',{'role_id':'test','experience':'A real test of application persistence.','portfolio':'','consent':True})
                req(f"/api/applications/{a['id']}/answer",{'turn':0,'answer':'I measured completed workflows.'})
                restarted=App(roles=[role],ai=AI(),start_worker=False)
                self.assertEqual(len(restarted.store.get(a['id'])['answers']),1)
                with restarted.store.job_lock() as acquired:self.assertTrue(acquired)
        finally:
            with psycopg.connect(url,autocommit=True) as conn:conn.execute(f'DROP SCHEMA {schema} CASCADE')
