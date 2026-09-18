"""Flat ClickUp support queue for candidate queries (approved 17 September 2026).

Hierarchy: Space "FlashSpace" (discovered from the candidate folder) ->
Folder "Teamrecrut Support" -> List "Candidate Queries" -> one task per
candidate support request.

Design rules (same as the per-candidate folder sync):
- Remote identity (folder/list/task ids) is persisted immediately after
  creation and never trusted from stale in-memory state.
- Reconciliation before creation: scan for a matching name, fail loudly on
  ambiguity. One flat list, not one list per candidate, so the team works a
  single queue at any query volume.
- The generated task description is app-owned; support conversation belongs
  in task comments on the ClickUp side. No bidirectional sync.
A sync failure must never block the candidate: the ticket is already saved
locally, and the sync is retried on the next request.
"""
import json
import os
import re
import threading
from .server import APIError

SUPPORT_FOLDER_NAME = 'Teamrecrut Support'
SUPPORT_LIST_NAME = 'Candidate Queries'
CANDIDATE_FOLDER_ENV = 'CLICKUP_CANDIDATE_FOLDER_ID'
SPACE_KEY = 'support-space-id'
FOLDER_KEY = 'support-folder-id'
LIST_KEY = 'support-list-id'
TASK_KEY = 'support-task:'  # settings key prefix: support-task:<ticket_id>
MAX_SCAN_PAGES = 50


class SupportQueueClickUp:
    """One flat List; one task per support request. Managed by Teamrecrut."""

    def __init__(self, store, clickup):
        # clickup: any object with .call(method, path, data) — the app's
        # existing CandidateFolderClickUp instance; ClickUp auth is shared.
        self.store = store
        self.clickup = clickup
        self.lock = threading.RLock()

    # ---- settings helpers ---------------------------------------------------
    def _setting(self, key):
        with self.store.db() as db:
            row = db.execute('SELECT value FROM settings WHERE key=?', (key,)).fetchone()
        return row['value'] if row else None

    def _save_setting(self, key, value):
        with self.store.db() as db:
            db.execute('INSERT INTO settings(key,value) VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value', (key, str(value)))

    # ---- space / folder / list ----------------------------------------------
    def space_id(self):
        """The FlashSpace space id, discovered once from the candidate folder."""
        cached = self._setting(SPACE_KEY)
        if cached and re.fullmatch(r'\d+', cached):
            return cached
        candidate = os.getenv(CANDIDATE_FOLDER_ENV, '')
        if not re.fullmatch(r'\d+', candidate):
            raise APIError(503, 'Configure CLICKUP_CANDIDATE_FOLDER_ID before enabling the support queue.')
        folder = self.clickup.call('GET', f'folder/{candidate}')
        space = folder.get('space', {}).get('id')
        if not space or not re.fullmatch(r'\d+', str(space)):
            raise APIError(502, 'Could not read the ClickUp space from the candidate folder.')
        self._save_setting(SPACE_KEY, str(space))
        return str(space)

    def ensure_folder(self):
        cached = self._setting(FOLDER_KEY)
        if cached and re.fullmatch(r'\d+', cached):
            return cached
        with self.lock:
            space = self.space_id()
            folders = self.clickup.call('GET', f'space/{space}/folder?archived=false').get('folders', [])
            match = [f for f in folders if f.get('name') == SUPPORT_FOLDER_NAME]
            if len(match) > 1:
                raise APIError(409, 'Multiple Teamrecrut Support folders. Administrator must reconcile them.')
            if match:
                found = match[0]
            else:
                found = self.clickup.call('POST', f'space/{space}/folder', {'name': SUPPORT_FOLDER_NAME})
            self._save_setting(FOLDER_KEY, str(found['id']))
        return str(found['id'])

    def ensure_list(self):
        cached = self._setting(LIST_KEY)
        if cached and re.fullmatch(r'\d+', cached):
            return cached
        with self.lock:
            folder = self.ensure_folder()
            lists = self.clickup.call('GET', f'folder/{folder}/list?archived=false').get('lists', [])
            match = [l for l in lists if l.get('name') == SUPPORT_LIST_NAME]
            if len(match) > 1:
                raise APIError(409, 'Multiple Candidate Queries lists. Administrator must reconcile them.')
            if match:
                found = match[0]
            else:
                found = self.clickup.call('POST', f'folder/{folder}/list',
                                          {'name': SUPPORT_LIST_NAME,
                                           'content': 'One task per candidate support request. Managed by Teamrecrut.'})
            self._save_setting(LIST_KEY, str(found['id']))
        return str(found['id'])

    # ---- task identity --------------------------------------------------------
    @staticmethod
    def task_name(ticket):
        return f"Support — {ticket['subject'][:80]} · {ticket['name'][:40]} · FS-{ticket['user_id'][:8]}"

    def find_task(self, lid, name):
        matches = []
        for page in range(MAX_SCAN_PAGES):
            result = self.clickup.call('GET', f'list/{lid}/task?include_closed=true&page={page}&subtasks=false')
            tasks = result.get('tasks', [])
            matches.extend(t for t in tasks if t.get('name') == name)
            if len(tasks) < 100 or result.get('last_page') is True:
                break
        else:
            raise APIError(409, 'Support list scan exceeded safety limit; manual reconciliation required.')
        if len(matches) > 1:
            raise APIError(409, 'Duplicate matching support tasks need reconciliation.')
        return matches[0]['id'] if matches else None

    # ---- content ---------------------------------------------------------------
    @staticmethod
    def description(ticket):
        lines = ['TEAMRECRUT SUPPORT REQUEST',
                 'Managed by the website. Put replies in task comments, not this generated description.',
                 f"Candidate: {ticket['name']}", f"Email: {ticket['email']}",
                 f"Account reference: FS-{ticket['user_id'][:8]}",
                 f"Request reference: FS-SUP-{ticket['id'][:8]}",
                 f"Raised: {ticket['created']}", '',
                 'SUBJECT', ticket['subject'], '',
                 'MESSAGE', ticket['message'], '',
                 'REPLY (recorded by the recruiter)', ticket['reply'] or 'No reply yet.',
                 f"App status: {ticket['status']}"]
        return '\n'.join(lines)

    # ---- sync --------------------------------------------------------------------
    def sync_ticket(self, ticket):
        """Create or update the ClickUp task for one request. Returns (task_id, url)."""
        lid = self.ensure_list()
        name = self.task_name(ticket)
        payload = {'name': name, 'description': self.description(ticket)}
        cached = self._setting(TASK_KEY + ticket['id'])
        tid = cached if cached and re.fullmatch(r'\d+', cached) else None
        if not tid:
            tid = self.find_task(lid, name)
        if tid:
            result = self.clickup.call('PUT', f'task/{tid}', payload)
        else:
            result = self.clickup.call('POST', f'list/{lid}/task', payload)
            tid = result['id']
            self._save_setting(TASK_KEY + ticket['id'], str(tid))
        return str(tid), result.get('url')
