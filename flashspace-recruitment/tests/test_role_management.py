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

    def test_restart_inserts_newly_added_seed_role_without_touching_edits(self):
        # Publishing via code: a role appended to the seed list must appear
        # after a restart even though the DB was already seeded once, and
        # existing rows (renamed, closed) must stay untouched.
        self.admin()
        seed=self.req('/api/admin/roles/growth')['body']
        result=self.req('/api/admin/roles/growth',self.payload(version=seed['version'],title='Renamed role'))
        self.assertEqual(result['status'],200)
        self.state(result['body'],'closed')
        import copy
        interior=copy.deepcopy(legacy.ROLE)
        interior['id']='interior-designer'
        interior['title']='Interior Designer'
        restart=RoleManagementApp(self.temp.name+'/test.db',[legacy.ROLE,interior],self.ai,self.cu,False)
        self.assertEqual(len(restart.role_repository.all()),2)
        self.assertEqual(restart.role_repository.get('growth')['title'],'Renamed role')
        self.assertEqual(restart.role_repository.get('growth')['state'],'closed')
        self.assertEqual(restart.role_repository.get('interior-designer')['title'],'Interior Designer')
        self.assertEqual(restart.role_repository.get('interior-designer')['state'],'published')
        # a plain restart with the same seeds stays at 2 (no duplicates)
        again=RoleManagementApp(self.temp.name+'/test.db',[legacy.ROLE,interior],self.ai,self.cu,False)
        self.assertEqual(len(again.role_repository.all()),2)

    def test_unpublished_seed_force_closes_published_role(self):
        # Code-driven takedown: a role that exists in the DB (e.g. created
        # via the admin API) is removed from the public site by adding it to
        # the seed list with published:false — every startup force-closes it.
        self.admin()
        data={k:v for k,v in legacy.ROLE.items() if k not in ('id','published')}
        created=self.app.role_repository.create(data,'synthetic-admin')
        self.state(self.app.role_repository.get(created['id']),'published')
        import copy
        takeover=copy.deepcopy(legacy.ROLE)
        takeover['id']=created['id']
        takeover['published']=False
        restart=RoleManagementApp(self.temp.name+'/test.db',[legacy.ROLE,takeover],self.ai,self.cu,False)
        role=restart.role_repository.get(created['id'])
        self.assertEqual(role['state'],'closed')
        with restart.store.db() as db:
            row=db.execute('SELECT updated_by FROM managed_roles WHERE id=?',(created['id'],)).fetchone()
        self.assertEqual(row['updated_by'],'seed-takedown')
        # closed roles are hidden from the public list
        public=[r for r in restart.role_repository.all() if r['published']]
        self.assertNotIn(created['id'],[r['id'] for r in public])
        # re-publishing later = flip the seed back to true; state then only
        # changes through the admin API (published seeds never overwrite)
        takeover['published']=True
        resumed=RoleManagementApp(self.temp.name+'/test.db',[legacy.ROLE,takeover],self.ai,self.cu,False)
        self.assertEqual(resumed.role_repository.get(created['id'])['state'],'closed')

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
