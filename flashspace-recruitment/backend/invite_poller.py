"""ClickUp-native interview invites (approved 21 September 2026).

The recruiter flips the "Interview Invite" dropdown (Yes/No) on a candidate
task in ClickUp; this poller notices and sends the candidate the assessment
invite on WhatsApp through the team's Chatwoot inbox. No recruiter dashboard
and no paid ClickUp automations are required — the trigger is a plain ClickUp
custom field scanned by a poll loop:

    python -m backend.invite_poller --once      (cron every ~2 minutes)
    python -m backend.invite_poller --dry-run   (show what would send)

Design rules:
- Candidate data is read from the task itself (app-owned descriptions): the
  Interview task carries the application reference, candidate name and role;
  the Profile task in the same List carries the phone number. There is no
  production-database coupling, so the poller runs anywhere the env vars are
  set — including this always-on ops box while the staging app sleeps.
- Setting Yes on an Interview task invites for that role. Setting Yes on the
  Profile task invites for every application of that candidate.
- One invite per Interview task per Yes. Flip No then Yes to re-send.
- Send failures retry on every cycle while the field stays Yes, and are
  reported as a ClickUp task comment only when the outcome changes (no
  comment spam on repeated identical failures). Success always comments.
- Missing Chatwoot configuration is reported per task, never crashes cron.

Environment: CLICKUP_API_TOKEN, CHATWOOT_URL, CHATWOOT_TOKEN,
CHATWOOT_ACCOUNT_ID, CHATWOOT_INBOX_ID, CLICKUP_CANDIDATE_FOLDER_ID,
INVITE_STATE_FILE (optional; default ~/.teamrecrut_invite_state.json).
"""
import json
import os
import re
import sys
import tempfile
import time
import urllib.request

INVITE_LINK = 'https://recrut.teamlens.co/'
FOLDER_ENV = 'CLICKUP_CANDIDATE_FOLDER_ID'
DEFAULT_FOLDER = '901612030752'  # Teamrecrut — Candidate (FlashSpace space)
FIELD_NAME = 'Interview Invite'
STATE_ENV = 'INVITE_STATE_FILE'
POLL_SECONDS = 120
IST_OFFSET_SECONDS = 5.5 * 3600

INVITE_TEXT = (
    'Dear {name},\n\n'
    'You have been shortlisted for {role} and your application has moved to the second round.\n'
    'Please give the assessment through the provided link: {link}\n\n'
    'Instructions:\n'
    '1. Sign in and make your candidate profile, fill all the details\n'
    '2. Go to Explore Jobs, apply for {role}, and appear for the interview\n\n'
    '— Team Stirring Minds'
)

RE_PHONE = re.compile(r'Phone:\s*\+?(\d[\d\s-]{7,16}\d)')
RE_NAME = re.compile(r'^Candidate:\s*(.+)$', re.M)
RE_ROLE = re.compile(r'^Role:\s*(.+)$', re.M)
RE_APPREF = re.compile(r'Application reference: FS-\w{8}\s*\((\w+)\)')


class PollerError(Exception):
    pass


# ─── ClickUp client ───────────────────────────────────────────────────────────
class ClickUpClient:
    def __init__(self, token=None, base='https://api.clickup.com/api/v2'):
        self.token = (token if token is not None else os.getenv('CLICKUP_API_TOKEN', '') or '').strip()
        self.base = base.rstrip('/')

    def configured(self):
        return bool(self.token)

    def call(self, method, path, data=None):
        if not self.token:
            raise PollerError('ClickUp is not configured (CLICKUP_API_TOKEN missing).')
        body = json.dumps(data).encode() if data is not None else None
        req = urllib.request.Request(
            self.base + '/' + path, data=body, method=method,
            headers={'Authorization': self.token, 'Content-Type': 'application/json'})
        try:
            with urllib.request.urlopen(req, timeout=25) as r:
                return json.loads(r.read().decode() or '{}')
        except urllib.error.HTTPError as e:
            raise PollerError(f'ClickUp {e.code} on {method} {path}: '
                              f'{e.read().decode("utf-8", "replace")[:160]}')
        except urllib.error.URLError as e:
            raise PollerError(f'ClickUp unreachable on {method} {path}: {e.reason}')


# ─── Chatwoot client (same API the team's chatwoot-bridge uses) ───────────────
class ChatwootClient:
    def __init__(self, url=None, token=None, account=None, inbox=None):
        self.url = (url or os.getenv('CHATWOOT_URL', 'https://support.stirringminds.com')).rstrip('/')
        self.token = (token if token is not None else os.getenv('CHATWOOT_TOKEN', '') or '').strip()
        self.account = (account or os.getenv('CHATWOOT_ACCOUNT_ID', '1')).strip()
        self.inbox = (inbox if inbox is not None else os.getenv('CHATWOOT_INBOX_ID', '') or '').strip()

    def configured(self):
        return bool(self.token and self.inbox)

    def call(self, method, path, data=None):
        body = json.dumps(data).encode() if data is not None else None
        req = urllib.request.Request(
            f'{self.url}/api/v1/accounts/{self.account}/{path}', data=body, method=method,
            headers={'api_access_token': self.token, 'Content-Type': 'application/json'})
        try:
            with urllib.request.urlopen(req, timeout=25) as r:
                return r.status, json.loads(r.read().decode() or '{}')
        except urllib.error.HTTPError as e:
            raise PollerError(f'Chatwoot {e.code} on {method} {path}: '
                              f'{e.read().decode("utf-8", "replace")[:160]}')
        except urllib.error.URLError as e:
            raise PollerError(f'Chatwoot unreachable on {method} {path}: {e.reason}')

    def find_or_create_contact(self, phone, name):
        status, data = self.call('GET', f'contacts/search?q={phone}')
        for contact in data.get('payload') or []:
            if (contact.get('phone_number') or '').replace(' ', '') in (phone, phone.replace(' ', '')):
                return contact['id']
        status, data = self.call('POST', 'contacts', {'inbox_id': int(self.inbox), 'name': name, 'phone_number': phone})
        contact = data.get('payload', {}).get('contact') or data.get('contact') or {}
        cid = contact.get('id') or data.get('id')
        if not cid:
            raise PollerError('Chatwoot contact create returned no id.')
        return cid

    def create_conversation(self, contact_id):
        status, data = self.call('POST', 'conversations',
                                 {'inbox_id': int(self.inbox), 'contact_id': contact_id})
        cid = data.get('id') or data.get('payload', {}).get('id')
        if not cid:
            raise PollerError('Chatwoot conversation create returned no id.')
        return cid

    def send_whatsapp(self, phone, name, text):
        """Find-or-create contact + conversation in the WhatsApp inbox, then send."""
        contact_id = self.find_or_create_contact(phone, name)
        conversation_id = self.create_conversation(contact_id)
        self.call('POST', f'conversations/{conversation_id}/messages',
                  {'content': text, 'message_type': 'outgoing'})
        return conversation_id


# ─── state (file-backed; atomic writes) ───────────────────────────────────────
def default_state_path():
    return os.getenv(STATE_ENV) or os.path.join(os.path.expanduser('~'), '.teamrecrut_invite_state.json')


def load_state(path):
    try:
        with open(path) as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return {'fields': {}, 'tasks': {}}
        data.setdefault('fields', {})
        data.setdefault('tasks', {})
        return data
    except (OSError, ValueError):
        return {'fields': {}, 'tasks': {}}


def save_state(path, state):
    d = os.path.dirname(os.path.abspath(path)) or '.'
    fd, tmp = tempfile.mkstemp(dir=d, prefix='.invite_state_', suffix='.tmp')
    try:
        with os.fdopen(fd, 'w') as f:
            json.dump(state, f, indent=1)
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


# ─── helpers ──────────────────────────────────────────────────────────────────
def _now_ist():
    t = time.gmtime(time.time() + IST_OFFSET_SECONDS)
    return time.strftime('%Y-%m-%d %H:%M IST', t)


def _normalize_phone(raw):
    digits = re.sub(r'\D', '', raw)
    if len(digits) == 10:
        return '+91' + digits  # candidates are Indian 10-digit numbers
    if len(digits) == 12 and digits.startswith('91'):
        return '+' + digits
    if digits:
        return '+' + digits.lstrip('+')
    return ''


def _mask(phone):
    return phone[:-4] + '****' if len(phone) > 4 else '****'


def _yes_selected(field, yes_option_id):
    """ClickUp task reads return the selected option's orderindex (int) or,
    on some builds, the option id (str). Handle both; None means unset."""
    value = field.get('value')
    if value is None:
        return False
    if isinstance(value, str):
        return value == yes_option_id
    options = field.get('type_config', {}).get('options') or []
    yes_order = next((o.get('orderindex') for o in options if o.get('id') == yes_option_id), None)
    return yes_order is not None and value == yes_order


def _invite_field(task, field_id):
    for f in task.get('custom_fields') or []:
        if f.get('id') == field_id:
            return f
    return None


def ensure_invite_field(cu, lid, state):
    """Find-or-create the Interview Invite dropdown on this List (cached)."""
    cached = state['fields'].get(lid)
    if cached and cached.get('fid') and cached.get('yes'):
        return cached
    found = None
    for f in cu.call('GET', f'list/{lid}/field').get('fields') or []:
        if f.get('name') == FIELD_NAME:
            found = f
            break
    if not found:
        created = cu.call('POST', f'list/{lid}/field', {
            'name': FIELD_NAME, 'type': 'drop_down',
            'type_config': {'placeholder': 'Send WhatsApp interview invite?',
                            'options': [{'name': 'Yes', 'order': 0}, {'name': 'No', 'order': 1}]}})
        # Creation responses nest the field object under 'field'.
        found = created.get('field') or created
    options = found.get('type_config', {}).get('options') or []
    yes = next((o['id'] for o in options if o.get('name') == 'Yes'), None)
    no = next((o['id'] for o in options if o.get('name') == 'No'), None)
    if not yes:
        raise PollerError(f'Interview Invite dropdown on list {lid} has no Yes option.')
    cached = {'fid': found['id'], 'yes': yes, 'no': no}
    state['fields'][lid] = cached
    return cached


def _list_tasks(cu, lid):
    tasks, page = [], 0
    while page < 50:
        res = cu.call('GET', f'list/{lid}/task?include_closed=true&page={page}&subtasks=false')
        batch = res.get('tasks') or []
        tasks.extend(batch)
        if len(batch) < 100 or res.get('last_page') is True:
            break
        page += 1
    return tasks


def _parse_interview(task):
    text = task.get('text_content') or ''
    name = (re.search(RE_NAME, text) or [None, task.get('name', 'Candidate')])[1].strip()
    role = (re.search(RE_ROLE, text) or [None, 'the role'])[1].strip()
    appref = (re.search(RE_APPREF, text) or [None, None])[1]
    return {'name': name, 'role': role, 'application_id': appref}


def _profile_phone(tasks):
    for t in tasks:
        if t.get('name', '').startswith('Candidate Profile'):
            m = re.search(RE_PHONE, t.get('text_content') or '')
            if m:
                return _normalize_phone(m.group(1))
    return ''


def _comment(cu, task_id, text):
    cu.call('POST', f'task/{task_id}/comment', {'comment_text': text})


# ─── the poll cycle ───────────────────────────────────────────────────────────
def run_once(cu, cw, state, folder=None, dry=False, log=None):
    """Scan every candidate List; send invites for tasks marked Yes.

    Returns a list of human-readable action lines (empty when nothing to do).
    """
    log = log or (lambda msg: None)
    folder = folder or os.getenv(FOLDER_ENV) or DEFAULT_FOLDER
    actions = []
    if not cu.configured():
        raise PollerError('ClickUp is not configured; set CLICKUP_API_TOKEN.')
    lists = cu.call('GET', f'folder/{folder}/list?archived=false').get('lists') or []
    for lst in lists:
        lid = lst['id']
        try:
            field = ensure_invite_field(cu, lid, state)
        except PollerError as exc:
            log(f'list {lst.get("name", lid)}: cannot ensure dropdown: {exc}')
            continue
        tasks = _list_tasks(cu, lid)
        profile = [t for t in tasks if t.get('name', '').startswith('Candidate Profile')]
        interviews = [t for t in tasks if t.get('name', '').startswith('Candidate Interview')]
        phone = _profile_phone(profile)
        profile_yes = any(_yes_selected(_invite_field(t, field['fid']) or {}, field['yes'])
                          for t in profile if _invite_field(t, field['fid']))
        for task in interviews:
            tid = task['id']
            entry = state['tasks'].setdefault(tid, {})
            yes = bool(_invite_field(task, field['fid'])
                       and _yes_selected(_invite_field(task, field['fid']), field['yes']))
            trigger = yes or profile_yes
            if not trigger:
                if entry.get('saw_yes'):
                    entry['saw_yes'] = False  # observed No/unset: a later Yes re-sends
                continue
            if entry.get('saw_yes') and entry.get('status') == 'sent':
                continue  # already handled; waiting for a No in between
            info = _parse_interview(task)
            label = f"{info['name']} · {info['role']}"
            if dry:
                actions.append(f'WOULD SEND invite to {label} ({task.get("name", "")[:60]})')
                continue
            entry['saw_yes'] = True
            try:
                if not cw.configured():
                    raise PollerError('Chatwoot is not configured '
                                      '(CHATWOOT_TOKEN / CHATWOOT_INBOX_ID missing).')
                if not phone:
                    raise PollerError('No phone number found on the candidate Profile task.')
                text = INVITE_TEXT.format(name=info['name'].split(' ')[0], role=info['role'], link=INVITE_LINK)
                conv = cw.send_whatsapp(phone, info['name'], text)
                entry['status'] = 'sent'
                entry['sent_at'] = _now_ist()
                entry['phone'] = _mask(phone)
                _comment(cu, tid,
                         f'Interview invite sent on WhatsApp to {entry["phone"]} at {entry["sent_at"]} '
                         f'(Chatwoot conversation #{conv}). Set the Interview Invite field to No and back '
                         f'to Yes to send again.')
                actions.append(f'SENT invite to {label} via Chatwoot conversation #{conv}')
                log(f'sent: {label}')
            except PollerError as exc:
                detail = str(exc)[:300]
                if entry.get('status') != 'failed: ' + detail:
                    try:
                        _comment(cu, tid,
                                 f'Interview invite NOT sent: {detail} The automation retries while this '
                                 f'field stays Yes.')
                        entry['status'] = 'failed: ' + detail
                        actions.append(f'FAILED invite to {label}: {detail[:120]}')
                        log(f'failed: {label}: {detail[:120]}')
                    except PollerError as cexc:
                        log(f'cannot comment on {tid}: {cexc}')
                entry['saw_yes'] = False  # retry next cycle
    if not dry:
        # Persist dropdown ids + progress even on partial failures.
        pass
    return actions


# ─── CLI ──────────────────────────────────────────────────────────────────────
def main(argv):
    args = set(argv)
    dry = '--dry-run' in args
    loop = '--loop' in args
    state_path = default_state_path()
    cu = ClickUpClient()
    cw = ChatwootClient()
    if not cu.configured():
        print('ClickUp is not configured; set CLICKUP_API_TOKEN.', file=sys.stderr)
        return 2
    while True:
        state = load_state(state_path)
        try:
            actions = run_once(cu, cw, state, dry=dry)
        except PollerError as exc:
            print(f'poll error: {exc}', file=sys.stderr)
            save_state(state_path, state)
            if not loop:
                return 1
            actions = []
        save_state(state_path, state)
        for line in actions:
            print(line)
        if not loop:
            return 0
        time.sleep(POLL_SECONDS)


if __name__ == '__main__':
    raise SystemExit(main(sys.argv[1:]))
