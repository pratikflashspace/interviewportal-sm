"""Persisted in-scope sidebar features. No email or AI scoring."""
import json
import re
import uuid
from urllib.parse import urlsplit
from .server import APIError, digest, hash_password, verify_password, now
from .workspace_hiring_sync import WorkspaceClickUp, save_hiring_stage
from .integrated_recordings import InterviewRecordingClickUp

STAGES=('applied','under_review','shortlisted','contacted','hired','rejected')
DEFAULT_SETTINGS={'preferred_location':'','work_mode':'any'}

class WorkspaceFeatures:
    def init_features(self):
        with self.store.db() as db:
            db.execute('CREATE TABLE IF NOT EXISTS workspace_records (key TEXT PRIMARY KEY, data TEXT NOT NULL, version INTEGER NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS workspace_events (id TEXT PRIMARY KEY, application_id TEXT NOT NULL REFERENCES applications(id), actor TEXT NOT NULL, stage TEXT NOT NULL, created TEXT NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS workspace_support (id TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id), subject TEXT NOT NULL, message TEXT NOT NULL, status TEXT NOT NULL, reply TEXT NOT NULL, created TEXT NOT NULL)')
        # Replace only the default workspace integration; preserve injected test
        # doubles/custom integrations. Legacy non-workspace runtimes unchanged.
        if type(self.clickup) is InterviewRecordingClickUp:self.clickup=WorkspaceClickUp(self.store)

    def record(self,key,default):
        with self.store.db() as db:row=db.execute('SELECT data,version FROM workspace_records WHERE key=?',(key,)).fetchone()
        return {'fields':json.loads(row['data']) if row else default,'version':row['version'] if row else 0}

    def write_record(self,key,body,allowed,default):
        if set(body)!={'fields','version'} or type(body['version']) is not int or not isinstance(body['fields'],dict) or set(body['fields'])-set(allowed):raise APIError(400,'Invalid settings fields.')
        with self.lock:
            old=self.record(key,default)
            if old['version']!=body['version']:raise APIError(409,'Saved data changed. Reload before saving.')
            fields={**old['fields'],**body['fields']}
            for k,v in fields.items():
                if k not in allowed or not isinstance(v,str) or len(v)>allowed[k]:raise APIError(400,'Invalid field value.')
            if 'work_mode' in fields and fields['work_mode'] not in ('any','remote','onsite','hybrid'):raise APIError(400,'Choose a supported work mode.')
            if fields.get('website'):
                p=urlsplit(fields['website'])
                if p.scheme!='https' or not p.netloc or p.username or p.password:raise APIError(400,'Use a valid HTTPS website.')
            with self.store.db() as db:
                row=db.execute('INSERT INTO workspace_records(key,data,version) VALUES (?,?,1) ON CONFLICT(key) DO UPDATE SET data=excluded.data,version=workspace_records.version+1 WHERE workspace_records.version=? RETURNING version',(key,json.dumps(fields),old['version'])).fetchone()
                if not row:raise APIError(409,'Saved data changed. Reload before saving.')
        return self.record(key,default)

    def tracking(self,a):
        record=self.record('application:'+a['id'],{'stage':'under_review' if a['status']=='completed' else 'applied'})
        with self.store.db() as db:events=[dict(r) for r in db.execute('SELECT stage,created FROM workspace_events WHERE application_id=? ORDER BY created,id',(a['id'],))]
        return {'id':a['id'],'role_title':a['role_title'],'name':a['name'],'created_at':a['created_at'],
                'interview_status':a['status'],'flow_version':2 if self.flow(a['id']) else 1,
                'stage':record['fields']['stage'],'version':record['version'],'events':events}

    def route(self,env,body):
        path=env.get('PATH_INFO','');method=env.get('REQUEST_METHOD')
        if path=='/api/workspace/settings':
            u=self.current_user(env)
            if method=='GET':return self.record('settings:'+u['id'],DEFAULT_SETTINGS if not u['admin'] else {}),[]
            if method=='POST' and not u['admin']:return self.write_record('settings:'+u['id'],body,{'preferred_location':200,'work_mode':20},DEFAULT_SETTINGS),[]
            raise APIError(405,'Method not allowed.')
        if path=='/api/workspace/password' and method=='POST':
            u=self.current_user(env);self.store.quota('password-change:'+u['id'],5,600)
            if set(body)!={'current_password','password','confirm_password'}:raise APIError(400,'Invalid password update.')
            if not isinstance(body['current_password'],str) or not verify_password(body['current_password'],u['password']):raise APIError(401,'Current password is incorrect.')
            _,password=self.credentials({'email':u['email'],'password':body['password']})
            if password!=body['confirm_password']:raise APIError(400,'Passwords do not match.')
            with self.store.db() as db:
                changed=db.execute('UPDATE users SET password=? WHERE id=? AND password=? RETURNING id',(hash_password(password),u['id'],u['password'])).fetchone()
                if not changed:raise APIError(409,'Password changed in another session. Sign in again.')
                db.execute('DELETE FROM sessions WHERE user_id=?',(u['id'],))
            return {'ok':True,'sign_in_required':True},[('Set-Cookie','tr_session=; Path=/; HttpOnly; SameSite=Strict; Max-Age=0'+('; Secure' if self.secure else ''))]
        if path=='/api/workspace/recruiter/company':
            self.current_user(env)
            default={'name':'Stirring Minds','website':'','description':''}
            if method=='GET':return self.record('company',default),[]
            if method=='POST':
                if body.get('fields',{}).get('name','Stirring Minds')!='Stirring Minds':raise APIError(400,'This release is for Stirring Minds only.')
                return self.write_record('company',body,{'name':100,'website':1000,'description':4000},default),[]
            raise APIError(405,'Method not allowed.')
        if path in ('/api/workspace/candidate/applications','/api/workspace/recruiter/applications') and method=='GET':
            u=self.current_user(env)
            if u['admin']:
                with self.store.db() as db:ids=[r['id'] for r in db.execute('SELECT id FROM applications')]
                apps=[self.store.get(i) for i in ids]
            else:apps=self.candidate_apps(u)
            return [self.tracking(a) for a in apps],[]
        match=re.fullmatch(r'/api/workspace/recruiter/applications/([\w-]+)/stage',path)
        if match and method=='POST':
            u=self.current_user(env)
            return save_hiring_stage(self,match[1],u,body),[]
        if path=='/api/workspace/recruiter/candidates' and method=='GET':
            self.current_user(env)
            with self.store.db() as db:rows=db.execute('SELECT DISTINCT users.id,users.name,users.email FROM users JOIN applications ON applications.user_id=users.id WHERE users.admin=0').fetchall()
            result=[]
            for row in rows:
                u=dict(row);profile=self.get_profile({**u,'admin':0})
                result.append({'id':u['id'],'name':u['name'],'email':u['email'],'profile':profile['fields'],'applications':[self.tracking(a) for a in self.candidate_apps(u)]})
            return result,[]
        if path=='/api/workspace/recruiter/analytics' and method=='GET':
            self.current_user(env)
            with self.store.db() as db:ids=[r['id'] for r in db.execute('SELECT id FROM applications')]
            apps=[self.store.get(i) for i in ids];completed=sum(a['status']=='completed' for a in apps)
            stages={s:0 for s in STAGES};jobs={}
            for a in apps:
                stages[self.tracking(a)['stage']]+=1
                jobs.setdefault(a['role_id'],{'title':a['role_title'],'applications':0,'completed_interviews':0})
                jobs[a['role_id']]['applications']+=1;jobs[a['role_id']]['completed_interviews']+=int(a['status']=='completed')
            return {'applications':len(apps),'completed_interviews':completed,'completion_rate':round(100*completed/len(apps),1) if apps else None,'stages':stages,'jobs':list(jobs.values())},[]
        if path in ('/api/workspace/support','/api/workspace/recruiter/support'):
            u=self.current_user(env)
            if method=='GET':
                with self.store.db() as db:
                    rows=db.execute('SELECT id,subject,message,status,reply,created FROM workspace_support'+('' if u['admin'] else ' WHERE user_id=?')+' ORDER BY created DESC',() if u['admin'] else (u['id'],)).fetchall()
                return [dict(r) for r in rows],[]
            if method=='POST' and path=='/api/workspace/support':
                self.store.quota('support:'+u['id'],5,3600)
                subject=body.get('subject');message=body.get('message')
                if not isinstance(subject,str) or not 3<=len(subject.strip())<=150 or not isinstance(message,str) or not 10<=len(message.strip())<=4000:raise APIError(400,'Enter a subject (3–150 characters) and message (10–4000 characters).')
                tid=uuid.uuid4().hex
                with self.store.db() as db:db.execute('INSERT INTO workspace_support VALUES (?,?,?,?,?,?,?)',(tid,u['id'],subject.strip(),message.strip(),'open','',now()))
                return {'id':tid,'status':'open'},[]
            raise APIError(405,'Method not allowed.')
        match=re.fullmatch(r'/api/workspace/recruiter/support/([a-f0-9]{32})',path)
        if match and method=='POST':
            self.current_user(env);reply=body.get('reply');status=body.get('status')
            if status not in ('open','resolved') or not isinstance(reply,str) or not 1<=len(reply.strip())<=4000:raise APIError(400,'Enter a reply and valid status.')
            with self.store.db() as db:
                row=db.execute('UPDATE workspace_support SET reply=?,status=? WHERE id=? RETURNING id',(reply.strip(),status,match[1])).fetchone()
                if not row:raise APIError(404,'Support request not found.')
            return {'ok':True},[]
        return super().route(env,body)
