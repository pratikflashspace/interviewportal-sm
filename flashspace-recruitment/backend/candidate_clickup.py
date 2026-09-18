"""Per-candidate ClickUp structure (approved 14 September 2026).

Hierarchy: Space "FlashSpace" -> Folder "Teamrecrut — Candidate" ->
one List per candidate -> "Candidate Profile" task + one "Candidate
Interview summary and transcript" task per applied role.

Design rules carried over from the role-list sync:
- Remote identity (task/list ids) is persisted immediately after creation and
  never trusted from stale in-memory application state.
- Reconciliation before creation: scan the candidate's own small List for a
  matching task name instead of the whole folder, then fail loudly on ambiguity.
- The generated task description is app-owned; recruiter notes belong in
  comments. No bidirectional sync; humans make hiring decisions.
"""
import json
import os
import re
from .server import APIError
from .workspace_hiring_sync import WorkspaceClickUp, STAGE_LABELS

CANDIDATE_FOLDER_ENV = 'CLICKUP_CANDIDATE_FOLDER_ID'
LIST_KEY = 'candidate-list:'  # settings key prefix: candidate-list:<user_id>
MAX_SCAN_PAGES = 50

SECTION_ORDER = [('personal', 'PERSONAL'), ('summary', 'SUMMARY'), ('education', 'EDUCATION'),
                 ('experience', 'EXPERIENCE'), ('projects', 'PROJECTS'), ('skills', 'SKILLS'),
                 ('certifications', 'CERTIFICATIONS'), ('links', 'LINKS'),
                 ('preferences', 'PREFERENCES'), ('resume', 'RESUME')]


class CandidateFolderClickUp(WorkspaceClickUp):
    """One List per candidate; Profile task + Interview tasks inside it."""

    # ---- settings helpers -------------------------------------------------
    def _setting(self, key):
        with self.store.db() as db:
            row = db.execute('SELECT value FROM settings WHERE key=?', (key,)).fetchone()
        return row['value'] if row else None

    def _save_setting(self, key, value):
        with self.store.db() as db:
            db.execute('INSERT INTO settings(key,value) VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value', (key, str(value)))

    # ---- folder / list management -----------------------------------------
    def candidate_folder_id(self):
        folder = os.getenv(CANDIDATE_FOLDER_ENV, '')
        if not re.fullmatch(r'\d+', folder):
            raise APIError(503, 'Configure CLICKUP_CANDIDATE_FOLDER_ID (Teamrecrut — Candidate folder) in Render.')
        return folder

    def candidate_list_id(self, a):
        """Find-or-create the candidate's own List; cache its id per user."""
        cached = self._setting(LIST_KEY + a['user_id'])
        if cached:
            return cached
        folder = self.candidate_folder_id()
        name = f"{a['name'][:60]} · FS-{a['user_id'][:8]}"
        lists = self.call('GET', f'folder/{folder}/list?archived=false')['lists']
        matches = [l for l in lists if l['name'] == name]
        if len(matches) > 1:
            raise APIError(409, 'Multiple candidate Lists with this name. Recruiter must reconcile them.')
        if matches:
            found = matches[0]
        else:
            found = self.call('POST', f'folder/{folder}/list', {
                'name': name,
                'content': 'One List per candidate. Profile task plus one Interview task per applied role. Managed by Teamrecrut.'})
        self._save_setting(LIST_KEY + a['user_id'], found['id'])
        return str(found['id'])

    # ---- task identity ------------------------------------------------------
    @staticmethod
    def profile_task_name(a):
        return f"Candidate Profile — {a['name'][:70]} · FS-{a['user_id'][:8]}"

    @staticmethod
    def interview_task_name(a):
        return f"Candidate Interview summary and transcript — {a['role_title'][:40]} · FS-{a['id'][:8]}"

    def find_task(self, lid, name):
        """Scan only this candidate's List; return (task_id, url) or (None, None)."""
        matches = []
        for page in range(MAX_SCAN_PAGES):
            result = self.call('GET', f'list/{lid}/task?include_closed=true&page={page}&subtasks=false')
            tasks = result.get('tasks', [])
            matches.extend(t for t in tasks if t.get('name') == name)
            if len(tasks) < 100 or result.get('last_page') is True:
                break
        else:
            raise APIError(409, 'Candidate List scan exceeded safety limit; manual reconciliation required.')
        if len(matches) > 1:
            raise APIError(409, 'Duplicate matching tasks in this candidate List need recruiter reconciliation.')
        return (matches[0]['id'], matches[0].get('url')) if matches else (None, None)

    # ---- content ------------------------------------------------------------
    @staticmethod
    def profile_description(a):
        """Structured profile sections for the Profile task description."""
        lines = ['TEAMRECRUT CANDIDATE PROFILE',
                 'Managed by the website. Put recruiter notes in task comments, not this generated description.',
                 f"Candidate: {a['name']}", f"Email: {a['email']}",
                 f"Account reference: FS-{a['user_id'][:8]} ({a['user_id']})", '']
        sections = a.get('_profile_sections') or {}
        for key, label in SECTION_ORDER:
            value = sections.get(key)
            if not value:
                continue
            lines += [label]
            if key == 'skills':
                lines += [', '.join(value.get('items', [])), '']
                continue
            if isinstance(value, dict) and 'items' in value:
                for item in value['items']:
                    lines += [f"- {k.replace('_', ' ').title()}: {v}" for k, v in item.items() if isinstance(v, str) and v.strip()]
                    lines += ['']
                if key == 'experience' and value.get('no_experience'):
                    lines += ['No work experience yet (candidate supplied).', '']
                continue
            for k, v in value.items():
                if isinstance(v, str) and v.strip():
                    lines += [f"{k.replace('_', ' ').title()}: {v}"]
            lines += ['']
        return '\n'.join(lines)

    @staticmethod
    def interview_description(a):
        """Transcript + report + hiring stage for the Interview task description."""
        ev = a.get('evaluation')
        lines = ['TEAMRECRUT INTERVIEW RECORD',
                 'Managed by the website. Put recruiter notes in task comments, not this generated description.',
                 f"Application reference: FS-{a['id'][:8]} ({a['id']})",
                 f"Candidate: {a['name']}", f"Role: {a['role_title']}",
                 f"Application status: {a['status']}", '',
                 'RELEVANT EXPERIENCE', a.get('experience') or 'Not supplied', '']
        if ev:
            lines += ['INTERVIEW SUMMARY', ev['summary'],
                      'Evidence-only report. No aggregate score assigned. Human review required.',
                      f"Model: {ev['model']} | Rubric: {ev['rubric_version']}", '']
            for c in ev['criteria']:
                lines += [c['name'], c['reason'],
                          f"Evidence: {c['evidence'] or 'No evidence'}",
                          f"Source: {c.get('source_id') or 'None'} | Confidence: {c.get('confidence', 'unspecified')} (model-assessed)", '']
        else:
            lines += ['INTERVIEW SUMMARY', 'Report pending. No evidence report has been generated yet.', '']
        lines += ['FULL INTERVIEW TRANSCRIPT']
        for i, t in enumerate(a['answers'], 1):
            prefix = f"[{t.get('stage', 'interview')} / {t.get('kind', 'question')}] " if t.get('flow_version') == 2 else ''
            lines += [f"Question {i}: {prefix}{t['question']}", f"Candidate: {t['answer']}", f"Saved: {t['at']}"]
            losses = t.get('focus_losses')
            if losses:
                lines.append(f"Attention: candidate left or switched away from the interview window {losses} time(s) during this answer. Recorded automatically.")
            lines.append('')
        stage = a.get('_hiring_stage')
        if stage:
            lines += ['RECRUITER HIRING DECISION',
                      'Current hiring stage: ' + STAGE_LABELS.get(stage, stage),
                      'Recorded by the authorised recruiter; not an AI hiring decision.',
                      'This hiring stage is separate from interview completion.']
        if a.get('recording_review_url'):
            lines += ['', 'INTERVIEW RECORDING',
                      a['recording_review_url'],
                      'Historic recording from an earlier pilot; recruiter login required. May be lost on server replacement.']
        return '\n'.join(lines)

    # ---- sync entry point ----------------------------------------------------
    def profile_sections(self, app, a):
        """Load the candidate's structured profile via the profile module."""
        try:
            from .candidate_profile import read_raw
            u = {'id': a['user_id'], 'email': a['email'], 'name': a['name']}
            data, _ = read_raw(app, u)
        except Exception:
            return {}
        sections = data.get('_candidate_sections', {})
        result = {key: sections[key] for key in dict(SECTION_ORDER) if key in sections}
        # Simple shared fields live at the top level of the profile record.
        personal = dict(result.get('personal', {}))
        for key in ('name', 'phone', 'summary'):
            if data.get(key):
                personal[key] = data[key]
        if personal:
            result['personal'] = personal
        resume = dict(result.get('resume', {}))
        if data.get('resume_url'):
            resume['resume_url'] = data['resume_url']
        if resume:
            result['resume'] = resume
        return result

    def sync(self, a, app=None):
        """Sync one application: ensure List + Profile task, then upsert Interview task."""
        lid = self.candidate_list_id(a)
        profile_a = {**a, '_profile_sections': self.profile_sections(app, a) if app else {}}
        # Hiring stage lives in workspace_records; put it on the Interview task.
        try:
            with self.store.db() as db:
                row = db.execute('SELECT data FROM workspace_records WHERE key=?', ('application:' + a['id'],)).fetchone()
            stage = json.loads(row['data']).get('stage') if row else None
        except Exception:
            stage = None
        if stage and stage in STAGE_LABELS:
            a = {**a, '_hiring_stage': stage}
        # Profile task: find-or-create once, then refresh description.
        pname = self.profile_task_name(a)
        ptid, _ = self.find_task(lid, pname)
        payload_p = {'name': pname, 'description': self.profile_description(profile_a)}
        if ptid:
            self.call('PUT', f'task/{ptid}', payload_p)
        else:
            self.call('POST', f'list/{lid}/task', payload_p)
        # Interview task: same reconciliation rules, scoped to this candidate's
        # List. Persist remote identity before returning.
        iname = self.interview_task_name(a)
        itid, iurl = self.find_task(lid, iname)
        payload_i = {'name': iname, 'description': self.interview_description(a)}
        if itid:
            result = self.call('PUT', f'task/{itid}', payload_i)
        else:
            result = self.call('POST', f'list/{lid}/task', payload_i)
            itid = result['id']
        iurl = result.get('url') or iurl
        with self.store.db() as db:
            db.execute('UPDATE applications SET task_id=?,task_url=? WHERE id=?', (str(itid), iurl, a['id']))
        return str(itid), iurl
