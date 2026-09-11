"""One initial question delivery plus two replays, per application/question.

Count server deliveries, not browser onended events: clients cannot reset the
limit via refresh, reconnect, new tabs or fake completion callbacks. Failed
provider requests refund their reservation; ambiguous process death retains it.
"""
from .server import APIError

MAX_DELIVERIES = 3


class PlaybackLedger:
    def __init__(self, store):
        self.store=store
        with store.db() as db:
            if getattr(store,'is_postgres',False):db.execute('SELECT pg_advisory_xact_lock(185168612)')
            db.execute('CREATE TABLE IF NOT EXISTS v2_question_playback (application_id TEXT NOT NULL REFERENCES applications(id), question_id TEXT NOT NULL, deliveries INTEGER NOT NULL, PRIMARY KEY(application_id,question_id))')

    def state(self, aid, qid):
        with self.store.db() as db:
            row=db.execute('SELECT deliveries FROM v2_question_playback WHERE application_id=? AND question_id=?',(aid,qid)).fetchone()
        count=row['deliveries'] if row else 0
        return {'deliveries':count,'initial_available':count==0,'replays_remaining':max(0,2-max(0,count-1)),
                'deliveries_remaining':max(0,MAX_DELIVERIES-count),'max_replays':2}

    def reserve(self, aid, qid):
        with self.store.db() as db:
            row=db.execute('''INSERT INTO v2_question_playback(application_id,question_id,deliveries) VALUES (?,?,1)
                ON CONFLICT(application_id,question_id) DO UPDATE SET deliveries=v2_question_playback.deliveries+1
                WHERE v2_question_playback.deliveries<? RETURNING deliveries''',(aid,qid,MAX_DELIVERIES)).fetchone()
        if row is None:raise APIError(429,'This question has already been played once and replayed twice. Read it on screen or continue listening without replay.')
        return row['deliveries']

    def refund(self, aid, qid):
        with self.store.db() as db:
            db.execute('UPDATE v2_question_playback SET deliveries=deliveries-1 WHERE application_id=? AND question_id=? AND deliveries>0',(aid,qid))
