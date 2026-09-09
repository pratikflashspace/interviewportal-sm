"""Privileged local/Render-shell maintenance. Never expose this as a web endpoint."""
import argparse,getpass,os,sqlite3
from pathlib import Path
from backend.server import Store,hash_password
p=argparse.ArgumentParser();s=p.add_subparsers(dest='command',required=True)
r=s.add_parser('reset-password');r.add_argument('email')
b=s.add_parser('backup');b.add_argument('destination')
a=p.parse_args();store=Store(os.getenv('DATABASE_PATH','data/flashspace.sqlite3'));store.init()
if a.command=='reset-password':
    with store.db() as db: user=db.execute('SELECT id,admin FROM users WHERE email=?',(a.email.strip().lower(),)).fetchone()
    if not user: raise SystemExit('No exact account match.')
    password=getpass.getpass('New password (not echoed): ')
    if len(password.strip())<(16 if user['admin'] else 12) or len(password)>128: raise SystemExit('Password is too short or too long.')
    if password!=getpass.getpass('Repeat password: '): raise SystemExit('Passwords do not match.')
    with store.db() as db:
        db.execute('UPDATE users SET password=? WHERE id=?',(hash_password(password.strip()),user['id']))
        db.execute('DELETE FROM sessions WHERE user_id=?',(user['id'],))
    print('Password reset. All sessions for this account revoked.')
else:
    dest=Path(a.destination)
    if dest.exists(): raise SystemExit('Destination exists; choose a new backup filename.')
    dest.parent.mkdir(parents=True,exist_ok=True)
    with sqlite3.connect(store.path) as src,sqlite3.connect(dest) as target:src.backup(target)
    os.chmod(dest,0o600)
    print('Consistent SQLite backup created. Store it securely outside the service disk.')
