"""Workspace-only human hiring decisions, using the existing durable sync worker.
No ClickUp status mapping, comments, email, or candidate scoring is introduced.
"""
import json
import uuid
from .server import APIError, now
from .integrated_recordings import InterviewRecordingClickUp

STAGE_LABELS={'applied':'Applied','under_review':'Under review','shortlisted':'Shortlisted',
              'contacted':'Contacted','hired':'Hired','rejected':'Rejected'}

class WorkspaceClickUp(InterviewRecordingClickUp):
    def description(self,a):
        content=super().description(a)
        # Only fixed labels + decision timestamp are exported. Internal actor ids
        # and support/profile records stay private to the application.
        with self.store.db() as db:
            row=db.execute('SELECT data FROM workspace_records WHERE key=?',('application:'+a['id'],)).fetchone()
            event=db.execute('SELECT created FROM workspace_events WHERE application_id=? ORDER BY created DESC,id DESC LIMIT 1',(a['id'],)).fetchone()
        if not row:return content
        stage=json.loads(row['data']).get('stage')
        if stage not in STAGE_LABELS:raise APIError(409,'Stored hiring stage needs administrator review.')
        lines=['','RECRUITER HIRING DECISION','Current hiring stage: '+STAGE_LABELS[stage],
               'Recorded by the authorised recruiter; not an AI hiring decision.']
        if event:lines.append('Last decision recorded: '+event['created'])
        lines.append('This hiring stage is separate from interview completion. Contacted is a recorded status, not proof an email was sent.')
        return content+'\n'+'\n'.join(lines)


def save_hiring_stage(app,aid,user,body):
    stage=body.get('stage');version=body.get('version')
    if set(body)!={'stage','version'} or not isinstance(stage,str) or stage not in STAGE_LABELS or type(version) is not int or version<0:
        raise APIError(400,'Choose a supported hiring stage and version.')
    if not user['admin'] or user['email'].strip().lower()!=app.recruiter_email():
        raise APIError(403,'Recruiter access required.')
    with app.lock,app.store.db() as db:
        # Serialize with application writes in either database. This leaves the
        # interview JSON untouched; failure of any later write rolls it back.
        locked=db.execute('UPDATE applications SET version=version WHERE id=? RETURNING data',(aid,)).fetchone()
        if not locked:raise APIError(404,'Application not found.')
        current=json.loads(locked['data'])
        if current['status']!='completed' and stage not in ('applied','rejected'):
            raise APIError(409,'Complete the interview before moving to review or selection.')
        if version==0:
            row=db.execute('INSERT INTO workspace_records(key,data,version) VALUES (?,?,1) ON CONFLICT(key) DO NOTHING RETURNING version',('application:'+aid,json.dumps({'stage':stage}))).fetchone()
        else:
            row=db.execute('UPDATE workspace_records SET data=?,version=version+1 WHERE key=? AND version=? RETURNING version',(json.dumps({'stage':stage}),'application:'+aid,version)).fetchone()
        if not row:raise APIError(409,'Application changed. Refresh before updating.')
        db.execute('INSERT INTO workspace_events VALUES (?,?,?,?,?)',(uuid.uuid4().hex,aid,user['id'],stage,now()))
        # In the SAME transaction as stage + audit event: a crash cannot save a
        # decision without leaving a durable sync job. Preserve remote task id.
        db.execute('UPDATE applications SET version=version+1,next_retry=0,failures=0,sync_error=NULL WHERE id=?',(aid,))
    app.job_wakeup.set()
    return app.tracking(app.store.get(aid))
