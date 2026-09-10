"""Database-backed recruiter role administration with integrated interview recording."""
import json
import re
import threading
import uuid
from .durable_server import DurableInterviewApp
from .server import APIError, now

FIELDS = {'title': 200, 'department': 100, 'location': 200, 'type': 100,
          'experience': 200, 'description': 2000, 'details': 5000}
STATES = ('draft', 'published', 'closed')


def validate_role(body):
    if not isinstance(body, dict):
        raise APIError(400, 'Invalid role.')
    role = {}
    for key, limit in FIELDS.items():
        value = body.get(key)
        if not isinstance(value, str) or not 1 <= len(value.strip()) <= limit:
            raise APIError(400, f'{key}: enter 1 to {limit} characters.')
        role[key] = value.strip()
    skills = body.get('skills')
    if (not isinstance(skills, list) or not 1 <= len(skills) <= 20
            or any(not isinstance(s, str) or not 1 <= len(s.strip()) <= 100 for s in skills)):
        raise APIError(400, 'Enter 1 to 20 skills, each up to 100 characters.')
    role['skills'] = list(dict.fromkeys(s.strip() for s in skills))
    return role


class RoleRepository:
    def __init__(self, store):
        self.store = store

    def initialize(self, seeds):
        with self.store.db() as db:
            if getattr(self.store, 'is_postgres', False):
                db.execute('SELECT pg_advisory_xact_lock(185168611)')
            else:
                db.execute('BEGIN IMMEDIATE')
            db.execute('CREATE TABLE IF NOT EXISTS managed_roles (id TEXT PRIMARY KEY, data TEXT NOT NULL, state TEXT NOT NULL, version INTEGER NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL, updated_by TEXT NOT NULL)')
            seeded = db.execute('SELECT value FROM settings WHERE key=?', ('managed-roles-seeded-v1',)).fetchone()
            if not seeded:
                for seed in seeds:
                    data = {k: seed[k] for k in (*FIELDS, 'skills')}
                    stamp = now()
                    db.execute('INSERT INTO managed_roles VALUES (?,?,?,?,?,?,?) ON CONFLICT(id) DO NOTHING',
                               (seed['id'], json.dumps(data), 'published' if seed['published'] else 'draft', 1, stamp, stamp, 'seed'))
                db.execute('INSERT INTO settings(key,value) VALUES (?,?) ON CONFLICT(key) DO NOTHING',
                           ('managed-roles-seeded-v1', 'true'))

    @staticmethod
    def decode(row):
        return {**json.loads(row['data']), 'id': row['id'], 'state': row['state'],
                'published': row['state'] == 'published', 'version': row['version'],
                'created_at': row['created_at'], 'updated_at': row['updated_at']}

    def all(self):
        with self.store.db() as db:
            return [self.decode(row) for row in db.execute('SELECT * FROM managed_roles ORDER BY created_at,id')]

    def create(self, body, actor):
        data = validate_role(body)
        identifier, stamp = 'role-' + uuid.uuid4().hex, now()
        with self.store.db() as db:
            db.execute('INSERT INTO managed_roles VALUES (?,?,?,?,?,?,?)',
                       (identifier, json.dumps(data), 'draft', 1, stamp, stamp, actor))
        return self.get(identifier)

    def get(self, identifier):
        with self.store.db() as db:
            row = db.execute('SELECT * FROM managed_roles WHERE id=?', (identifier,)).fetchone()
        if row is None:
            raise APIError(404, 'Role not found.')
        return self.decode(row)

    def update(self, identifier, body, actor, state_only=False):
        version = body.get('version')
        if type(version) is not int or version < 1:
            raise APIError(400, 'A current role version is required.')
        stamp = now()
        with self.store.db() as db:
            if state_only:
                state = body.get('state')
                if state not in STATES:
                    raise APIError(400, 'Choose draft, published or closed.')
                cursor = db.execute('UPDATE managed_roles SET state=?,version=version+1,updated_at=?,updated_by=? WHERE id=? AND version=? RETURNING id',
                                    (state, stamp, actor, identifier, version))
            else:
                data = validate_role(body)
                cursor = db.execute('UPDATE managed_roles SET data=?,version=version+1,updated_at=?,updated_by=? WHERE id=? AND version=? RETURNING id',
                                    (json.dumps(data), stamp, actor, identifier, version))
            if cursor.fetchone() is None:
                exists = db.execute('SELECT id FROM managed_roles WHERE id=?', (identifier,)).fetchone()
                if not exists:
                    raise APIError(404, 'Role not found.')
                raise APIError(409, 'Another recruiter changed this role. Reload roles before saving again.')
        return self.get(identifier)


class RoleManagementApp(DurableInterviewApp):
    def __init__(self, db_path=None, roles=None, ai=None, clickup=None, start_worker=True):
        super().__init__(db_path, roles, ai, clickup, False)
        self.role_repository = RoleRepository(self.store)
        self.role_repository.initialize(self.roles)
        self.roles = self.role_repository.all()
        if start_worker:
            threading.Thread(target=self.worker, daemon=True).start()

    def route(self, env, body):
        path, method = env.get('PATH_INFO', ''), env.get('REQUEST_METHOD')
        match = re.fullmatch(r'/api/admin/roles(?:/([a-z0-9-]{1,50})(/state)?)?', path)
        if match:
            user = self.current_user(env)
            if not user['admin']:
                raise APIError(403, 'Recruiter access is required.')
            with self.lock:
                identifier, state_path = match.groups()
                if method == 'GET':
                    if state_path:
                        raise APIError(404, 'Not found.')
                    return (self.role_repository.get(identifier) if identifier else self.role_repository.all()), []
                if method == 'POST':
                    if identifier:
                        return self.role_repository.update(identifier, body, user['id'], bool(state_path)), []
                    return self.role_repository.create(body, user['id']), []
            raise APIError(405, 'Method not allowed.')
        if method == 'GET' and path == '/api/roles':
            return [{k: role[k] for k in ('id', *FIELDS, 'skills')}
                    for role in self.role_repository.all() if role['published']], []
        if method == 'POST' and path == '/api/applications':
            with self.lock:
                self.roles = self.role_repository.all()
                return super().route(env, body)
        return super().route(env, body)


def create_app():
    from .integrated_recording import create_app as recording_app
    return recording_app()
