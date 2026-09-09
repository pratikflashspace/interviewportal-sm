"""Durable PostgreSQL storage for Render Free. SQLite remains test/local-only.
All SQL is application-owned; values remain psycopg-bound parameters.
"""
import os
import time
from contextlib import contextmanager
from urllib.parse import urlsplit,parse_qs

DDL=[
'''CREATE TABLE IF NOT EXISTS users(id TEXT PRIMARY KEY,email TEXT UNIQUE NOT NULL,name TEXT NOT NULL,password TEXT NOT NULL,admin INTEGER NOT NULL DEFAULT 0,created TEXT NOT NULL)''',
'''CREATE TABLE IF NOT EXISTS sessions(token TEXT PRIMARY KEY,user_id TEXT REFERENCES users(id) ON DELETE CASCADE,expires DOUBLE PRECISION NOT NULL)''',
'''CREATE TABLE IF NOT EXISTS applications(id TEXT PRIMARY KEY,user_id TEXT NOT NULL REFERENCES users(id),role_id TEXT NOT NULL,data TEXT NOT NULL,version INTEGER NOT NULL DEFAULT 1,synced_version INTEGER NOT NULL DEFAULT 0,task_id TEXT,task_url TEXT,next_retry DOUBLE PRECISION NOT NULL DEFAULT 0,failures INTEGER NOT NULL DEFAULT 0,sync_error TEXT,UNIQUE(user_id,role_id))''',
'''CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY,value TEXT NOT NULL)''',
'''CREATE TABLE IF NOT EXISTS quotas(key TEXT PRIMARY KEY,n INTEGER NOT NULL,expires DOUBLE PRECISION NOT NULL)''',
'''CREATE INDEX IF NOT EXISTS fs_sessions_expiry ON sessions(expires)''',
'''CREATE INDEX IF NOT EXISTS fs_apps_user ON applications(user_id)''',
'''CREATE INDEX IF NOT EXISTS fs_apps_retry ON applications(next_retry)''',
'''CREATE INDEX IF NOT EXISTS fs_quotas_expiry ON quotas(expires)'''
]

def validate_url(url):
    parsed=urlsplit(url)
    if parsed.scheme not in ('postgres','postgresql') or not parsed.hostname or not parsed.path.strip('/'):
        raise RuntimeError('DATABASE_URL must be a PostgreSQL connection string. Do not paste it into GitHub or chat.')
    if parsed.hostname not in ('localhost','127.0.0.1','::1') and parse_qs(parsed.query).get('sslmode',[''])[0] not in ('require','verify-ca','verify-full'):
        raise RuntimeError('Use the database provider connection string with sslmode=require or stronger.')
    return url

class Connection:
    def __init__(self,connection):self.connection=connection
    def execute(self,sql,params=()):
        # Current query set contains no '?' operators or literal placeholders.
        sql=sql.replace("data->>'created_at'","(data::jsonb)->>'created_at'")
        return self.connection.execute(sql.replace('?','%s'),params)
    def executescript(self,script):
        for sql in script.split(';'):
            if sql.strip():self.execute(sql)


def make_store(base,error_type):
    class PostgresStore(base):
        is_postgres=True
        def __init__(self,url):
            self.url=validate_url(url)
            try:
                import psycopg
                from psycopg.rows import dict_row
            except ImportError:raise RuntimeError('Install requirements.txt before using PostgreSQL.') from None
            self.driver=psycopg;self.row_factory=dict_row
        @contextmanager
        def db(self):
            # Short-lived connections let Neon sleep when there is no web/job traffic.
            # connect_timeout avoids hanging all request threads on a failed database.
            connection=self.driver.connect(self.url,row_factory=self.row_factory,connect_timeout=15,prepare_threshold=None)
            try:
                yield Connection(connection)
                connection.commit()
            except Exception:
                connection.rollback();raise
            finally:connection.close()
        def init(self):
            with self.db() as db:
                db.execute('SELECT pg_advisory_xact_lock(185168609)')
                for sql in DDL:db.execute(sql)
        def quota(self,key,limit,seconds=86400):
            current=time.time()
            with self.db() as db:
                row=db.execute('''INSERT INTO quotas(key,n,expires) VALUES (?,1,?)
                    ON CONFLICT(key) DO UPDATE SET
                    n=CASE WHEN quotas.expires<=? THEN 1 ELSE quotas.n+1 END,
                    expires=CASE WHEN quotas.expires<=? THEN EXCLUDED.expires ELSE quotas.expires END
                    WHERE quotas.expires<=? OR quotas.n<? RETURNING n''',
                    (key,current+seconds,current,current,current,limit)).fetchone()
                if not row:raise error_type(429,'Usage limit reached. Please wait before trying again.')
        @contextmanager
        def job_lock(self):
            # Transaction-scoped advisory lock also works with a transaction pooler.
            # Held on a separate connection, so overlapping deploys cannot run jobs twice.
            with self.db() as db:
                row=db.execute('SELECT pg_try_advisory_xact_lock(185168610) AS acquired').fetchone()
                yield bool(row['acquired'])
    return PostgresStore

def select_store(base,error_type,db_path=None):
    # Tests pass an explicit temporary SQLite path, never contact a live DATABASE_URL.
    if db_path is not None:return base(db_path)
    url=os.getenv('DATABASE_URL','').strip()
    if url:return make_store(base,error_type)(url)
    if os.getenv('REQUIRE_DATABASE_URL','').lower()=='true' or os.getenv('RENDER') or os.getenv('RENDER_EXTERNAL_URL'):
        raise RuntimeError('DATABASE_URL is required on Render. Local SQLite would lose candidate data on restarts.')
    return base(os.getenv('DATABASE_PATH','data/flashspace.sqlite3'))
