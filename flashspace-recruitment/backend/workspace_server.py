"""Branch-only Teamrecrut workspaces. No automatic account provisioning.
MFA deferred by creator; Google and release integration remain separate work.
"""
import json
import re
import threading
import uuid
from http.cookies import SimpleCookie
from urllib.parse import urlsplit
from .interview_release import InterviewRelease
from .server import APIError, digest, hash_password, now, text, verify_password
from .workspace_features import WorkspaceFeatures

RECRUITER_EMAIL='team@stirringminds.com'
PROFILE_FIELDS = {
    'candidate': {'name':100, 'phone':40, 'summary':2000, 'education':4000,
                  'experience':4000, 'skills':2000, 'projects':4000,
                  'certifications':2000, 'preferences':2000, 'resume_url':1000},
    'recruiter': {'name':100, 'phone':40, 'designation':150, 'bio':2000},
}

class WorkspaceApp(WorkspaceFeatures, InterviewRelease):
    def bootstrap_admin(self):
        # An independently authorized administrative process must provision it.
        pass

    def __init__(self,*args,**kwargs):
        start=kwargs.pop('start_worker',True)
        super().__init__(*args,start_worker=False,**kwargs)
        with self.store.db() as db:
            db.execute('CREATE TABLE IF NOT EXISTS workspace_profiles (user_id TEXT PRIMARY KEY REFERENCES users(id), data TEXT NOT NULL, version INTEGER NOT NULL)')
            rows=db.execute('SELECT LOWER(TRIM(email)) AS normalized, COUNT(*) AS n FROM users GROUP BY LOWER(TRIM(email)) HAVING COUNT(*)>1').fetchall()
            if rows:raise RuntimeError('Duplicate normalized account emails require administrator reconciliation.')
            db.execute('CREATE UNIQUE INDEX IF NOT EXISTS workspace_email_normalized ON users(LOWER(TRIM(email)))')
        self.init_features()
        if start:threading.Thread(target=self.worker,daemon=True).start()

    def recruiter_email(self):return RECRUITER_EMAIL

    def user_json(self,u):
        if not u:return None
        return {**super().user_json(u),'role':'recruiter' if u['admin'] else 'candidate'}

    def session(self,user):
        key,value=super().session(user)
        return key,value.replace('fs_session=','tr_session=',1)

    def current_user(self,env,required=True):
        cookies=SimpleCookie()
        try:cookies.load(env.get('HTTP_COOKIE',''));value=cookies.get('tr_session')
        except Exception:value=None
        adapted={**env,'HTTP_COOKIE':'fs_session='+value.value if value else ''}
        u=super().current_user(adapted,required)
        if not u:return None
        if u['admin'] and u['email'].strip().lower()!=self.recruiter_email():
            raise APIError(403,'This recruiter account is not authorised.')
        path=env.get('PATH_INFO','')
        recruiter_path=path.startswith('/api/admin/') or path.startswith('/api/workspace/recruiter/') or bool(re.fullmatch(r'/api/recordings/[a-f0-9]{32}/(media|remove)',path))
        candidate_path=(path.startswith('/api/applications') or path.startswith('/api/v2/') or path.startswith('/api/workspace/candidate/') or (path.startswith('/api/recordings/') and not recruiter_path) or not path)
        if recruiter_path and not u['admin']:raise APIError(403,'Recruiter access required.')
        if candidate_path and u['admin']:raise APIError(403,'Candidate access required.')
        return u

    def credentials(self,body):
        email=text(body,'email',3,254).lower()
        if not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+',email):raise APIError(400,'Enter a valid email address.')
        password=body.get('password')
        if not isinstance(password,str) or not 12<=len(password)<=128:raise APIError(400,'Use a password of 12–128 characters.')
        return email,password

    def authenticate_role(self,env,body,role,action):
        if role=='recruiter' and action!='login':raise APIError(404,'Not found.')
        self.store.quota('workspace-auth-ip:'+env.get('REMOTE_ADDR','unknown'),30,600)
        email,password=self.credentials(body)
        self.store.quota('workspace-auth-email:'+digest(email),10,600)
        with self.lock:
            with self.store.db() as db:
                found=db.execute('SELECT * FROM users WHERE LOWER(TRIM(email))=?',(email,)).fetchone()
                u=dict(found) if found else None
            if action=='signup':
                if set(body)-{'email','password','confirm_password','name'}:raise APIError(400,'Unsupported signup fields.')
                if body.get('confirm_password')!=password:raise APIError(400,'Passwords do not match.')
                if u or email==self.recruiter_email():raise APIError(409,'This email is unavailable for candidate registration.')
                name=text(body,'name',2,100)
                u={'id':str(uuid.uuid4()),'email':email,'name':name,'admin':0}
                with self.store.db() as db:
                    db.execute('INSERT INTO users VALUES (?,?,?,?,0,?)',(u['id'],email,name,hash_password(password),now()))
            else:
                valid=verify_password(password,u['password']) if u else False
                if not u:hash_password(password)
                right_role=bool(u and bool(u['admin'])==(role=='recruiter'))
                allowed=role!='recruiter' or email==self.recruiter_email()
                if not valid or not right_role or not allowed:raise APIError(401,'Email or password is incorrect for this account type.')
                # Creator explicitly deferred MFA. Never auto-provision/promote.
        return self.user_json(u),[self.session(u)]

    def get_profile(self,u):
        with self.store.db() as db:row=db.execute('SELECT data,version FROM workspace_profiles WHERE user_id=?',(u['id'],)).fetchone()
        role='recruiter' if u['admin'] else 'candidate'
        data=json.loads(row['data']) if row else {}
        return {'role':role,'email':u['email'],'version':row['version'] if row else 0,
                'fields':{k:data.get(k,u['name'] if k=='name' else '') for k in PROFILE_FIELDS[role]}}

    def save_profile(self,u,body):
        role='recruiter' if u['admin'] else 'candidate'
        if set(body)!={'version','fields'} or type(body.get('version')) is not int:raise APIError(400,'Invalid profile update.')
        fields=body.get('fields')
        if not isinstance(fields,dict) or set(fields)-set(PROFILE_FIELDS[role]):raise APIError(400,'Unsupported profile fields. Role and email cannot be edited here.')
        with self.lock:
            old=self.get_profile(u)
            if body['version']!=old['version']:raise APIError(409,'Profile changed. Reload before saving.')
            updated=dict(old['fields'])
            for key,value in fields.items():
                if not isinstance(value,str) or len(value)>PROFILE_FIELDS[role][key]:raise APIError(400,'Profile field is invalid or too long.')
                if key=='name' and len(value.strip())<2:raise APIError(400,'Enter your name.')
                if key=='resume_url' and value:
                    parsed=urlsplit(value)
                    if parsed.scheme!='https' or not parsed.netloc or parsed.username or parsed.password:raise APIError(400,'Use an HTTPS resume link without credentials.')
                updated[key]=value.strip()
            with self.store.db() as db:
                row=db.execute('INSERT INTO workspace_profiles(user_id,data,version) VALUES (?,?,1) ON CONFLICT(user_id) DO UPDATE SET data=excluded.data,version=workspace_profiles.version+1 WHERE workspace_profiles.version=? RETURNING version',
                    (u['id'],json.dumps(updated),old['version'])).fetchone()
                if not row:raise APIError(409,'Profile changed. Reload before saving.')
                db.execute('UPDATE users SET name=? WHERE id=?',(updated['name'],u['id']))
        return self.get_profile({**u,'name':updated['name']})

    def candidate_apps(self,u):
        with self.store.db() as db:ids=[r['id'] for r in db.execute('SELECT id FROM applications WHERE user_id=?',(u['id'],))]
        return [self.store.get(aid) for aid in ids]

    def route(self,env,body):
        path=env.get('PATH_INFO','');method=env.get('REQUEST_METHOD')
        if path in ('/api/login','/api/register'):raise APIError(410,'Choose Candidate or Recruiter before signing in.')
        match=re.fullmatch(r'/api/auth/(candidate|recruiter)/(login|signup|google)',path)
        if match:
            if method!='POST':raise APIError(405,'POST required.')
            role,action=match.groups()
            if action=='google':raise APIError(404,'Google authentication is not configured.')
            return self.authenticate_role(env,body,role,action)
        if path=='/api/logout' and method=='POST':
            cookies=SimpleCookie();cookies.load(env.get('HTTP_COOKIE',''));token=cookies.get('tr_session')
            if token:
                with self.store.db() as db:db.execute('DELETE FROM sessions WHERE token=?',(digest(token.value),))
            return {'ok':True},[('Set-Cookie','tr_session=; Path=/; HttpOnly; SameSite=Strict; Max-Age=0'+('; Secure' if self.secure else ''))]
        if path=='/api/workspace/profile':
            u=self.current_user(env)
            if method=='GET':return self.get_profile(u),[]
            if method=='POST':return self.save_profile(u,body),[]
            raise APIError(405,'Method not allowed.')
        if path=='/api/workspace/candidate/recommendations' and method=='GET':
            u=self.current_user(env);apps=self.candidate_apps(u);applied={a['role_id'] for a in apps}
            skills={s.lower() for a in apps for s in a['role_snapshot'].get('skills',[])}
            departments={a['role_snapshot'].get('department') for a in apps}
            matches=[]
            for role in self.role_repository.all():
                if not role['published'] or role['id'] in applied:continue
                shared=sorted(skills & {s.lower() for s in role.get('skills',[])})
                if shared or role['department'] in departments:
                    matches.append({'role':role,'reason':'Similar skills: '+', '.join(shared) if shared else 'Same department as a role you applied for.'})
            return matches,[]
        return super().route(env,body)
