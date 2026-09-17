"""Per-candidate ClickUp structure tests: one List per candidate, Profile task,
one Interview task per application. ClickUp network boundary is fully faked;
no live account is contacted.
"""
import json
import os
import tempfile
import unittest
from unittest.mock import patch
import test_backend as legacy
from backend.server import APIError
from backend.candidate_clickup import CandidateFolderClickUp
from backend.v2_flow import create_flow, commit_answer, FlowError

FOLDER = '901612030752'


class FakeFolderAPI:
    """In-memory stand-in for the ClickUp REST surface used by the sync."""

    def __init__(self):
        self.lists = {}       # list_id -> {'name','tasks': {task_id: task}}
        self.tasks_by_list = {}
        self.next_id = 1000
        self.fail = False

    def _new_id(self):
        self.next_id += 1
        return str(self.next_id)

    def call(self, method, path, data=None):
        if self.fail:
            raise APIError(502, 'Synthetic ClickUp failure')
        if method == 'GET' and path.startswith('folder/') and path.endswith('/list?archived=false'):
            return {'lists': [{'id': lid, 'name': l['name']} for lid, l in self.lists.items()]}
        if method == 'POST' and path.startswith('folder/') and path.endswith('/list'):
            lid = self._new_id()
            self.lists[lid] = {'name': data['name'], 'tasks': {}}
            return {'id': lid, 'name': data['name']}
        if method == 'GET' and path.startswith('list/') and '/task' in path:
            lid = path.split('/')[1]
            tasks = self.lists.get(lid, {}).get('tasks', {})
            return {'tasks': [{'id': tid, 'name': t['name'], 'url': t.get('url')} for tid, t in tasks.items()], 'last_page': True}
        if method == 'POST' and path.startswith('list/') and path.endswith('/task'):
            lid = path.split('/')[1]
            tid = self._new_id()
            url = 'https://clickup.example/t/' + tid
            self.lists[lid]['tasks'][tid] = {'name': data['name'], 'description': data.get('description', ''), 'url': url}
            return {'id': tid, 'name': data['name'], 'url': url}
        if method == 'PUT' and path.startswith('task/'):
            tid = path.split('/')[1]
            for l in self.lists.values():
                if tid in l['tasks']:
                    l['tasks'][tid]['name'] = data['name']
                    l['tasks'][tid]['description'] = data.get('description', '')
                    return {'id': tid, 'url': l['tasks'][tid].get('url')}
            raise APIError(500, 'task missing in fake')
        raise APIError(500, 'unhandled fake route: %s %s' % (method, path))

    def all_tasks(self):
        out = []
        for lid, l in self.lists.items():
            for tid, t in l['tasks'].items():
                out.append({'list': lid, 'list_name': l['name'], 'id': tid, **t})
        return out


class CandidateFolderTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        env = patch.dict(os.environ, {
            'ADMIN_EMAIL': '', 'APP_ORIGIN': 'http://localhost:8000',
            'CLICKUP_CANDIDATE_FOLDER_ID': FOLDER, 'MAX_AI_CALLS_PER_DAY': '500'})
        env.start()
        self.addCleanup(env.stop)
        import test_backend as legacy
        from test_workspace_interview_journey import Provider, BoundaryClickUp
        self.provider = Provider()
        self.ai = object.__new__(type('FakeEvidenceAI', (), {}))
        # Reuse the journey Provider through the real EvidenceOnlyAI path.
        from backend.v2_endpoint import EvidenceOnlyAI
        self.ai = object.__new__(EvidenceOnlyAI)
        self.ai.provider = self.provider
        from backend.workspace_server import WorkspaceApp
        self.app = WorkspaceApp(db_path=self.tmp.name + '/test.db', roles=[legacy.ROLE], ai=self.ai,
                                start_worker=False, recording_root=self.tmp.name + '/recordings')
        self.assertIsInstanceOf = None
        self.api = FakeFolderAPI()
        self.clickup = CandidateFolderClickUp(self.app.store)
        self.clickup.call = self.api.call
        self.app.clickup = self.clickup
        with self.app.store.db() as db:
            db.execute('INSERT INTO settings(key,value) VALUES (?,?)', ('v2-bank:growth', 'sales'))
        self.cookie = ''

    # -- helpers reuse the real request path --
    def req(self, path, body=None, method=None, cookie=None, origin='http://localhost:8000'):
        import io
        method = method or ('POST' if body is not None else 'GET')
        data = json.dumps(body or {}).encode()
        env = {'REQUEST_METHOD': method, 'PATH_INFO': path, 'REMOTE_ADDR': 'synthetic',
               'CONTENT_TYPE': 'application/json', 'CONTENT_LENGTH': str(len(data)),
               'wsgi.input': io.BytesIO(data), 'HTTP_ORIGIN': origin,
               'HTTP_X_REQUESTED_WITH': 'Flashspace', 'HTTP_COOKIE': self.cookie if cookie is None else cookie}
        result = {}

        def start(s, h):
            result.update(status=int(s.split()[0]), headers=dict(h))
        out = b''.join(self.app(env, start))
        result['body'] = json.loads(out) if out[:1] in (b'{', b'[', b'n') else out
        if 'Set-Cookie' in result['headers']:
            self.cookie = result['headers']['Set-Cookie'].split(';')[0]
        return result

    def ok(self, path, body=None, **kw):
        r = self.req(path, body, **kw)
        self.assertEqual(r['status'], 200, r)
        return r['body']

    def signup(self, email='candidate@example.com', name='Synthetic Candidate'):
        self.ok('/api/auth/candidate/signup', {'name': name, 'email': email,
                'password': 'synthetic-password-123', 'confirm_password': 'synthetic-password-123', 'phone': '9876543210'})

    def apply_v2(self, role_id='growth'):
        return self.ok('/api/v2/applications', {'role_id': role_id,
                       'experience': 'Synthetic experience for per-candidate structure testing.',
                       'portfolio': 'https://example.com/resume',
                       'consent': True, 'consent_version': 'flashspace-sarvam-conversation-v2'})

    def complete_interview(self, base, f):
        for i in range(10):
            qid = f['active']['id']
            answer = 'Synthetic response %d with a concrete contribution.' % i
            self.ok(base + '/draft', {'question_id': qid, 'revision': 0, 'transcript': answer}) if False else None
            self.ok(base + '/end-check', {'question_id': qid, 'version': f['version'], 'answer': answer})
            f = self.ok(base + '/answer', {'event_id': 'cand-event-%d' % i, 'version': f['version'],
                                           'question_id': qid, 'answer': answer})
        return f

    def test_one_list_two_roles_profile_plus_interview_tasks(self):
        self.signup(email='ravi@example.com', name='Ravi Kumar')
        f1 = self.apply_v2()
        aid1 = f1['application_id']
        f = self.complete_interview('/api/v2/applications/' + aid1, f1)
        self.app.work_once()

        lists = self.api.all_tasks()
        list_names = {t['list_name'] for t in lists}
        self.assertEqual(list_names, {'Ravi Kumar · FS-' + self._uid()[:8]},
                         'exactly one candidate List, named with the account reference')
        self.assertEqual(len({t['list'] for t in lists}), 1)
        task_names = sorted(t['name'] for t in lists)
        self.assertEqual(task_names, sorted([
            'Profile — Ravi Kumar · FS-' + self._uid()[:8],
            'Interview — Growth & Partnerships · FS-' + aid1[:8]]))
        profile = next(t for t in lists if t['name'].startswith('Profile'))
        self.assertIn('TEAMRECRUT CANDIDATE PROFILE', profile['description'])
        self.assertIn('Email: candidate@example.com'.replace('candidate', 'ravi'), profile['description'])
        interview = next(t for t in lists if t['name'].startswith('Interview'))
        self.assertIn('FULL INTERVIEW TRANSCRIPT', interview['description'])
        self.assertIn('Synthetic response 9', interview['description'])
        self.assertIn('Synthetic experience for per-candidate', interview['description'])

    def _uid(self, email='ravi@example.com'):
        with self.app.store.db() as db:
            return db.execute('SELECT id FROM users WHERE email=?', (email,)).fetchone()[0]

    def test_second_role_reuses_list_and_profile_task(self):
        # Both roles seeded from the start so the same candidate can apply twice.
        from backend.workspace_server import WorkspaceApp
        second_role = {'id': 'marketing', 'title': 'AI Marketing', 'department': 'Marketing',
                       'location': 'Remote', 'type': 'Full-time', 'experience': '0-2 years',
                       'description': 'Own marketing.', 'details': 'Grow awareness.',
                       'skills': ['Marketing'], 'published': True}
        saved_app = self.app
        self.app = WorkspaceApp(db_path=self.tmp.name + '/test2.db', roles=[legacy.ROLE, second_role],
                                ai=self.ai, start_worker=False, recording_root=self.tmp.name + '/recordings')
        self.app.clickup = CandidateFolderClickUp(self.app.store)
        self.app.clickup.call = self.api.call
        with self.app.store.db() as db:
            db.execute('INSERT INTO settings(key,value) VALUES (?,?)', ('v2-bank:marketing', 'marketing'))
            db.execute('INSERT INTO settings(key,value) VALUES (?,?)', ('v2-bank:growth', 'sales'))
        self.cookie = ''
        self.signup(email='meera@example.com', name='Meera Patel')
        f1 = self.apply_v2('growth')
        base1 = '/api/v2/applications/' + f1['application_id']
        self.complete_interview(base1, f1)
        self.app.work_once()
        before_lists = len(self.api.lists)
        f2 = self.apply_v2('marketing')  # same candidate, second role
        base2 = '/api/v2/applications/' + f2['application_id']
        self.assertNotEqual(f2['application_id'], f1['application_id'])
        self.complete_interview(base2, f2)
        self.app.work_once()
        self.assertEqual(len(self.api.lists), before_lists, 'no second List for the same candidate')
        tasks = [t['name'] for t in self.api.all_tasks()]
        profile_names = [n for n in tasks if n.startswith('Profile')]
        self.assertEqual(len(profile_names), 1, 'Profile task is never duplicated')
        interview_names = [n for n in tasks if n.startswith('Interview')]
        self.assertEqual(len(interview_names), 2, 'one Interview task per applied role')
        self.assertIn('Interview — AI Marketing', interview_names[0] + interview_names[1])
        self.app = saved_app

    def test_sync_failure_keeps_application_retry_pending(self):
        self.signup(email='fail@example.com', name='Failing Sync')
        f = self.apply_v2()
        self.api.fail = True
        self.app.work_once()
        a = self.app.store.get(f['application_id'])
        self.assertEqual(a['sync_status'], 'Retry pending')

    def test_hiring_stage_appears_on_interview_task(self):
        self.signup(email='stage@example.com', name='Stage Candidate')
        f1 = self.apply_v2()
        aid = f1['application_id']
        self.complete_interview('/api/v2/applications/' + aid, f1)
        self.app.work_once()
        # Move the hiring stage through the real recruiter route.
        from backend.workspace_server import RECRUITER_EMAIL
        with self.app.store.db() as db:
            db.execute('INSERT INTO users VALUES (?,?,?,?,1,?)',
                       ('synthetic-recruiter', RECRUITER_EMAIL, 'Recruiter', 'x' * 16, '2026-09-14'))
        from backend.server import hash_password
        with self.app.store.db() as db:
            db.execute('UPDATE users SET password=? WHERE email=?', (hash_password('synthetic-password-123'), RECRUITER_EMAIL))
        self.ok('/api/auth/recruiter/login', {'email': RECRUITER_EMAIL, 'password': 'synthetic-password-123'})
        self.ok('/api/workspace/recruiter/applications/' + aid + '/stage', {'stage': 'shortlisted', 'version': 0})
        self.app.work_once()
        tasks = self.api.all_tasks()
        interview = next(t for t in tasks if t['name'].startswith('Interview'))
        self.assertIn('Current hiring stage: Shortlisted', interview['description'])

    def test_profile_sections_from_real_profile_data(self):
        self.signup(email='sections@example.com', name='Sections Candidate')
        # Save a structured profile section through the real API.
        base = self.req('/api/workspace/candidate/profile')['body']['version']
        view = self.ok('/api/workspace/candidate/profile', {'version': base, 'section': 'skills', 'value': {'items': ['Python', 'SQL']}})
        self.assertEqual(view['sections']['skills']['items'], ['Python', 'SQL'])
        f = self.apply_v2()
        self.complete_interview('/api/v2/applications/' + f['application_id'], f)
        self.app.work_once()
        profile = next(t for t in self.api.all_tasks() if t['name'].startswith('Profile'))
        self.assertIn('SKILLS', profile['description'])
        self.assertIn('Python, SQL', profile['description'])

    def test_folder_env_required(self):
        with patch.dict(os.environ, {'CLICKUP_CANDIDATE_FOLDER_ID': ''}):
            self.signup(email='nofolder@example.com', name='No Folder')
            f = self.apply_v2()
            self.app.work_once()
            a = self.app.store.get(f['application_id'])
            self.assertEqual(a['sync_status'], 'Retry pending')
            self.assertIn('CLICKUP_CANDIDATE_FOLDER_ID', a['sync_error'])


if __name__ == '__main__':
    unittest.main()


class FocusLossTests(CandidateFolderTests):
    """Anti-cheat: focus losses travel with each answer into the ClickUp transcript."""

    def test_focus_loss_recorded_per_answer(self):
        self.signup(email='focus@example.com', name='Focus Candidate')
        f1 = self.apply_v2()
        base = '/api/v2/applications/' + f1['application_id']
        f = f1
        for i in range(10):
            qid = f['active']['id']
            answer = 'Synthetic focus response %d with a concrete contribution.' % i
            self.ok(base + '/end-check', {'question_id': qid, 'version': f['version'], 'answer': answer})
            f = self.ok(base + '/answer', {'event_id': 'focus-event-%d' % i, 'version': f['version'],
                                           'question_id': qid, 'answer': answer,
                                           'focus_losses': 1 if i == 0 else 0})
            self.assertEqual(f['answers'][-1].get('focus_losses'), 1 if i == 0 else 0)
        self.app.work_once()
        interview = next(t for t in self.api.all_tasks() if t['name'].startswith('Interview'))
        self.assertIn('left or switched away from the interview window 1 time(s)', interview['description'])

    def test_focus_loss_validation(self):
        from backend.v2_flow import commit_answer, FlowError
        flow = create_flow('sales', 7)
        with self.assertRaises(FlowError):
            commit_answer(flow, 'event-12345', 0, flow['active']['id'], 'A valid answer.', 'now', -1)
        with self.assertRaises(FlowError):
            commit_answer(flow, 'event-12345', 0, flow['active']['id'], 'A valid answer.', 'now', 1000)
        f, fresh = commit_answer(flow, 'event-12345', 0, flow['active']['id'], 'A valid answer.', 'now', 2)
        self.assertTrue(fresh)
        self.assertEqual(f['answers'][0]['focus_losses'], 2)
