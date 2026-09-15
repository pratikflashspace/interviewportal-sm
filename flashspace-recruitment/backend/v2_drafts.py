"""Finalized speech drafts survive page refresh; never treated as scored answers.

Optimistic draft revisions avoid silent cross-tab overwrites. Raw audio and
partial hypotheses are never persisted. Ownership/current-question checks belong
to the authenticated endpoint. Old question drafts are ignored on resume.
"""
from .server import APIError,now

class DraftStore:
    def __init__(self,store):
        self.store=store
        with store.db() as db:
            if getattr(store,'is_postgres',False):db.execute('SELECT pg_advisory_xact_lock(185168613)')
            db.execute('CREATE TABLE IF NOT EXISTS v2_answer_drafts (application_id TEXT NOT NULL REFERENCES applications(id), question_id TEXT NOT NULL, transcript TEXT NOT NULL, revision INTEGER NOT NULL, updated_at TEXT NOT NULL, PRIMARY KEY(application_id,question_id))')
    def get(self,aid,qid):
        with self.store.db() as db:
            row=db.execute('SELECT transcript,revision,updated_at FROM v2_answer_drafts WHERE application_id=? AND question_id=?',(aid,qid)).fetchone()
        return dict(row) if row else {'transcript':'','revision':0,'updated_at':None}
    def save(self,aid,qid,text,revision):
        if not isinstance(text,str) or len(text)>6000 or type(revision) is not int or revision<0:
            raise APIError(400,'Invalid draft or revision.')
        with self.store.db() as db:
            if revision==0:
                row=db.execute('INSERT INTO v2_answer_drafts(application_id,question_id,transcript,revision,updated_at) VALUES (?,?,?,1,?) ON CONFLICT(application_id,question_id) DO NOTHING RETURNING revision',
                               (aid,qid,text,now())).fetchone()
            else:
                row=db.execute('UPDATE v2_answer_drafts SET transcript=?,revision=revision+1,updated_at=? WHERE application_id=? AND question_id=? AND revision=? RETURNING revision',
                               (text,now(),aid,qid,revision)).fetchone()
        if row is None:raise APIError(409,'Draft changed in another session. Reload saved draft before editing.')
        return {'transcript':text,'revision':row['revision']}
