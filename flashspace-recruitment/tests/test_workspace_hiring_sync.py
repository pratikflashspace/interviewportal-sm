"""Real workspace/worker hiring-decision paths; ClickUp boundary mocked, no live writes.

Updated for the per-candidate ClickUp structure (one List per candidate; Profile
task + Interview tasks). The decision/sync/retry contracts under test are
unchanged: stage queues a durable sync job, retries preserve the decision, stale
writes conflict, and the generated description carries only fixed labels.
"""
import json
from contextlib import contextmanager
from unittest.mock import patch
import test_workspace_server as ws
from backend.server import APIError
from backend.candidate_clickup import CandidateFolderClickUp


class FakeCandidateAPI:
    """In-memory ClickUp stand-in for the per-candidate folder."""

    def __init__(self):
        self.lists = {}
        self.tasks = {}
        self.next_id = 100
        self.fail = False

    def call(self, method, path, data=None):
        if self.fail:
            raise APIError(502, 'Synthetic upstream failure')
        if method == 'GET' and path.startswith('folder/') and '/list' in path:
            return {'lists': [{'id': lid, 'name': l['name']} for lid, l in self.lists.items()]}
        if method == 'POST' and path.startswith('folder/') and '/list' in path:
            lid = str(self.next_id); self.next_id += 1
            self.lists[lid] = {'name': data['name'], 'task_ids': []}
            return {'id': lid, 'name': data['name']}
        if method == 'GET' and path.startswith('list/') and '/task' in path:
            lid = path.split('/')[1]
            rows = [{'id': tid, 'name': t['name'], 'url': t.get('url')}
                    for tid, t in self.tasks.items() if t['list'] == lid]
            return {'tasks': rows, 'last_page': True}
        if method == 'POST' and path.startswith('list/') and path.endswith('/task'):
            lid = path.split('/')[1]
            tid = str(self.next_id); self.next_id += 1
            url = 'https://example.com/task/' + tid
            self.tasks[tid] = {'list': lid, 'name': data['name'], 'description': data.get('description', ''), 'url': url}
            return {'id': tid, 'url': url}
        if method == 'PUT' and path.startswith('task/'):
            tid = path.split('/')[1]
            task = self.tasks[tid]
            task['name'] = data['name']
            task['description'] = data.get('description', '')
            return {'id': tid, 'url': task['url']}
        raise APIError(500, 'unhandled fake route')

    def task_named(self, prefix):
        return [t for t in self.tasks.values() if t['name'].startswith(prefix)]


class HiringSyncTests(ws.WorkspaceTests):
    def prepare(self):
        self.signup()
        r = self.req('/api/applications', {'role_id': 'growth', 'experience': 'Synthetic hiring sync application.', 'consent': True})
        self.assertEqual(r['status'], 200, r); aid = r['body']['id']
        a = self.app.store.get(aid); a['status'] = 'completed'
        a['answers'] = [{'question': 'Synthetic question', 'answer': 'Synthetic preserved answer', 'at': 'test'}]
        a['evaluation'] = {'summary': 'Synthetic preserved report', 'score': None, 'model': 'fake', 'rubric_version': 'test', 'criteria': []}
        a['recording_review_url'] = 'https://test.example/interview-review?application=' + aid
        self.app.store.save(a)
        with self.app.store.db() as db:
            db.execute('UPDATE applications SET synced_version=version WHERE id=?', (aid,))
        self.recruiter(); self.login_recruiter(); self.app.job_wakeup.clear()
        self.assertIsInstance(self.app.clickup, CandidateFolderClickUp)
        self.api = FakeCandidateAPI()
        self.app.clickup.call = self.api.call
        return aid

    def move(self, aid, stage='shortlisted', version=0):
        return self.req('/api/workspace/recruiter/applications/' + aid + '/stage', {'stage': stage, 'version': version})

    def test_decision_queues_and_syncs_into_candidate_list(self):
        aid = self.prepare(); before = self.app.store.get(aid)
        self.assertEqual(self.move(aid)['status'], 200)
        after = self.app.store.get(aid)
        self.assertEqual(after['version'], before['version'] + 1); self.assertEqual(after['sync_status'], 'Queued')
        self.assertTrue(self.app.job_wakeup.is_set())
        for key in ('status', 'answers', 'evaluation', 'recording_review_url'):
            self.assertEqual(after[key], before[key])
        self.app.work_once()
        self.assertEqual(self.app.store.get(aid)['sync_status'], 'Synced')
        # One candidate List; Profile + Interview tasks inside it.
        self.assertEqual(len(self.api.lists), 1, 'exactly one List for this candidate')
        self.assertEqual(len(self.api.task_named('Profile')), 1)
        interviews = self.api.task_named('Interview')
        self.assertEqual(len(interviews), 1)
        for text in ('Current hiring stage: Shortlisted', 'Synthetic preserved answer',
                     'Synthetic preserved report', 'INTERVIEW RECORDING'):
            self.assertIn(text, interviews[0]['description'])
        self.assertNotIn('actor', interviews[0]['description'])
        # Remote identity persisted on the application row.
        updated = self.app.store.get(aid)
        self.assertIn('/task/', updated['task_url'])

    def test_network_failure_then_retry_preserves_decision(self):
        aid = self.prepare(); self.move(aid)
        self.api.fail = True
        self.app.work_once()
        self.assertEqual(self.app.store.get(aid)['sync_status'], 'Retry pending')
        self.assertEqual(self.app.tracking(self.app.store.get(aid))['stage'], 'shortlisted')
        self.api.fail = False
        with self.app.store.db() as db:
            db.execute('UPDATE applications SET next_retry=0 WHERE id=?', (aid,))
        self.app.work_once()
        self.assertEqual(self.app.store.get(aid)['sync_status'], 'Synced')
        self.assertEqual(len(self.api.task_named('Interview')), 1, 'no duplicate Interview task after retry')

    def test_stale_decision_does_not_duplicate_event_or_queue(self):
        aid = self.prepare(); self.move(aid); self.app.work_once(); before = self.app.store.get(aid)
        self.assertEqual(self.move(aid, 'hired', 0)['status'], 409)
        after = self.app.store.get(aid)
        self.assertEqual(after['version'], before['version']); self.assertEqual(after['sync_status'], 'Synced')
        self.assertEqual(len(self.app.tracking(after)['events']), 1)
        self.assertEqual(len(self.api.task_named('Interview')), 1)

    def test_stage_audit_and_queue_roll_back_together(self):
        aid = self.prepare(); before = self.app.store.get(aid); original = self.app.store.db

        class FailQueue:
            def __init__(self, db):
                self.db = db

            def execute(self, sql, params=()):
                if sql.startswith('UPDATE applications SET version=version+1'):
                    raise RuntimeError('Synthetic queue write failure')
                return self.db.execute(sql, params)

        @contextmanager
        def broken():
            with original() as db:
                yield FailQueue(db)

        with patch.object(self.app.store, 'db', broken):
            self.assertEqual(self.move(aid)['status'], 500)
        after = self.app.store.get(aid)
        self.assertEqual(after['version'], before['version']); self.assertEqual(after['sync_status'], 'Synced')
        self.assertEqual(self.app.tracking(after)['events'], [])
        self.assertEqual(self.app.record('application:' + aid, {})['version'], 0)

    def test_new_decision_during_sync_remains_queued(self):
        aid = self.prepare(); self.move(aid)
        original = self.app.clickup.call
        fired = []

        def delayed(method, path, data=None):
            result = original(method, path, data)
            # Fire exactly once, mid-sync: the per-candidate flow makes several
            # ClickUp calls, so only the first may inject the new decision.
            if not fired:
                fired.append(True)
                self.assertEqual(self.move(aid, 'hired', 1)['status'], 200)
            return result

        self.app.clickup.call = delayed
        self.app.work_once()
        self.assertEqual(self.app.store.get(aid)['sync_status'], 'Queued')
        self.app.work_once()
        self.assertEqual(self.app.store.get(aid)['sync_status'], 'Synced')
        interviews = self.api.task_named('Interview')
        self.assertEqual(len(interviews), 1)
        self.assertIn('Current hiring stage: Hired', interviews[0]['description'])

    def test_invalid_stage_payload_rejected(self):
        aid = self.prepare()
        for stage, version in (([], 0), ('shortlisted', -1), ('shortlisted', True), ('unapproved', 0)):
            self.assertEqual(self.move(aid, stage, version)['status'], 400)
        self.assertEqual(self.app.store.get(aid)['sync_status'], 'Synced')

    def test_no_decision_keeps_existing_description(self):
        aid = self.prepare()
        a = self.app.store.get(aid)
        self.assertNotIn('RECRUITER HIRING DECISION', self.app.clickup.interview_description(a))

if __name__ == '__main__':
    unittest.main()
