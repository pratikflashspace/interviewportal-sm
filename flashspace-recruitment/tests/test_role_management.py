"""Recruiter authorization, persistent roles and application snapshot regression tests."""
import os
import uuid
import unittest
from unittest.mock import patch
import test_backend as legacy
from test_durable_backend import DurableBackendTests as DurableTests
from backend.role_server import RoleManagementApp, RoleRepository


class RoleTests(DurableTests):
    def setUp(self):
        super().setUp()
        self.app = RoleManagementApp(self.temp.name+'/test.db', [legacy.ROLE], self.ai, self.cu, False)

    def admin(self):
        self.register('recruiter@example.com')
        with self.app.store.db() as db:
            db.execute('UPDATE users SET admin=1 WHERE email=?', ('recruiter@example.com',))

    def payload(self, **changes):
        return {**{k:v for k,v in legacy.ROLE.items() if k not in ('id','published')}, **changes}

    def new_role(self):
        response = self.req('/api/admin/roles', self.payload())
        self.assertEqual(response['status'], 200)
        return response['body']

    def state(self, role, state):
        result = self.req('/api/admin/roles/'+role['id']+'/state', {'version':role['version'], 'state':state})
        self.assertEqual(result['status'], 200)
        return result['body']

    def test_admin_access_and_csrf(self):
        self.assertEqual(self.req('/api/admin/roles')['status'],401)
        self.register()
        self.assertEqual(self.req('/api/admin/roles')['status'],403)
        self.assertEqual(self.req('/api/admin/roles',self.payload())['status'],403)
        self.admin()
        self.assertEqual(self.req('/api/admin/roles',self.payload(),origin='https://evil.example')['status'],403)

    def test_full_role_lifecycle(self):
        self.admin()
        role=self.new_role()
        self.assertEqual(role['state'],'draft')
        self.assertNotIn(role['id'],[r['id'] for r in self.req('/api/roles')['body']])
        role=self.state(role,'published')
        self.assertIn(role['id'],[r['id'] for r in self.req('/api/roles')['body']])
        role=self.state(role,'closed')
        self.assertNotIn(role['id'],[r['id'] for r in self.req('/api/roles')['body']])
        self.state(role,'draft')

    def test_create_cannot_publish_or_override_identity(self):
        self.admin()
        role=self.req('/api/admin/roles', self.payload(id='growth',state='published',published=True))['body']
        self.assertNotEqual(role['id'],'growth')
        self.assertEqual(role['state'],'draft')

    def test_optimistic_concurrency_and_input_validation(self):
        self.admin()
        role=self.new_role()
        path='/api/admin/roles/'+role['id']
        self.assertEqual(self.req(path,self.payload(version=1,title='Updated title'))['status'],200)
        self.assertEqual(self.req(path,self.payload(version=1,title='Stale title'))['status'],409)
        self.assertEqual(self.req(path+'/state',{'version':1,'state':'published'})['status'],409)
        self.assertEqual(self.req(path+'/state',{'version':2,'state':'deleted'})['status'],400)
        for field,value in (('skills',[]),('skills',[1]),('title',''),('description','a'*2001)):
            self.assertEqual(self.req('/api/admin/roles',self.payload(**{field:value}))['status'],400)
        self.assertEqual(self.req(path,self.payload(version=True))['status'],400)

    def test_restart_does_not_reseed_or_overwrite_edits(self):
        self.admin()
        seed=self.req('/api/admin/roles/growth')['body']
        result=self.req('/api/admin/roles/growth',self.payload(version=seed['version'],title='Renamed role'))
        self.assertEqual(result['status'],200)
        self.state(result['body'],'closed')
        restart=RoleManagementApp(self.temp.name+'/test.db',[legacy.ROLE],self.ai,self.cu,False)
        self.assertEqual(len(restart.role_repository.all()),1)
        self.assertEqual(restart.role_repository.get('growth')['title'],'Renamed role')
        self.assertEqual(restart.role_repository.get('growth')['state'],'closed')

    def test_rename_preserves_snapshot_and_clickup_mapping(self):
        self.register()
        a=self.apply()
        with self.app.store.db() as db:
            db.execute('INSERT INTO settings(key,value) VALUES (?,?)',('list:growth','existing-list'))
        self.admin()
        response=self.req('/api/admin/roles/growth',self.payload(version=1,title='New role name'))
        self.assertEqual(response['status'],200)
        self.assertEqual(self.app.store.get(a['id'])['role_snapshot']['title'],legacy.ROLE['title'])
        from backend.server import ClickUp
        with patch.object(ClickUp,'call',side_effect=AssertionError('must reuse mapping')):
            self.assertEqual(ClickUp(self.app.store).list_id(response['body']),'existing-list')

    def test_closed_role_blocks_new_applications_but_existing_can_finish(self):
        self.register()
        a=self.apply()
        candidate_cookie=self.cookie
        self.admin()
        role=self.req('/api/admin/roles/growth')['body']
        self.state(role,'closed')
        self.register('newcandidate@example.com')
        self.assertEqual(self.req('/api/applications',{'role_id':'growth','experience':'A relevant fictional experience.','consent':True})['status'],404)
        self.cookie=candidate_cookie
        for i in range(4):
            self.assertEqual(self.req('/api/applications/'+a['id']+'/answer',{'turn':i,'answer':'I measured a fictional result.'})['status'],200)
        self.assertEqual(self.req('/api/applications/'+a['id']+'/finish',{})['status'],200)

    def test_public_output_excludes_management_metadata(self):
        role=self.req('/api/roles')['body'][0]
        for key in ('version','state','created_at','updated_at','updated_by','published'):
            self.assertNotIn(key,role)

    def test_unpublished_roles(self):
        # Database is now authoritative, rather than mutating self.app.roles in memory.
        self.admin()
        role=self.req('/api/admin/roles/growth')['body']
        self.state(role,'draft')
        self.assertEqual(self.req('/api/roles')['body'],[])


@unittest.skipUnless(os.getenv('TEST_POSTGRES_URL'),'Disposable PostgreSQL is not configured')
class PostgresRolesTests(unittest.TestCase):
    def test_seed_edit_publish_restart_and_mapping_preservation(self):
        import psycopg
        from test_postgres_integration import schema_test_url
        url=os.environ['TEST_POSTGRES_URL'];schema='fs_roles_'+uuid.uuid4().hex
        with psycopg.connect(url,autocommit=True) as conn:
            conn.execute(f'CREATE SCHEMA {schema}')
        try:
            scoped=schema_test_url(url,schema)
            with patch.dict(os.environ,{'DATABASE_URL':scoped,'ADMIN_EMAIL':'','REQUIRE_DATABASE_URL':'','RENDER':''}):
                app=RoleManagementApp(roles=[legacy.ROLE],ai=legacy.FakeAI(),clickup=legacy.FakeClickUp(),start_worker=False)
                repo=app.role_repository
                seed=repo.get('growth')
                data={k:v for k,v in legacy.ROLE.items() if k not in ('id','published')}
                created=repo.create(data,'synthetic-admin')
                repo.update(created['id'],{'version':1,'state':'published'},'synthetic-admin',True)
                repo.update('growth',{**data,'title':'Edited in PostgreSQL','version':seed['version']},'synthetic-admin')
                restarted=RoleManagementApp(roles=[legacy.ROLE],ai=legacy.FakeAI(),clickup=legacy.FakeClickUp(),start_worker=False)
                self.assertEqual(len(restarted.role_repository.all()),2)
                self.assertEqual(restarted.role_repository.get('growth')['title'],'Edited in PostgreSQL')
                self.assertEqual(restarted.role_repository.get(created['id'])['state'],'published')
        finally:
            with psycopg.connect(url,autocommit=True) as conn:
                conn.execute(f'DROP SCHEMA {schema} CASCADE')
