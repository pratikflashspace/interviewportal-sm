"""ClickUp-native interview invites (approved 21 September 2026).

Recruiters flip the "Interview Invite" dropdown (Yes/No) on a candidate task
in ClickUp; this poller notices and sends the candidate the assessment invite
on WhatsApp through the team's Chatwoot inbox. No recruiter dashboard and no
paid ClickUp automations are required — the trigger is a plain ClickUp custom
field scanned by a poll loop:

    python -m backend.invite_poller --once      (cron every ~2 minutes)
    python -m backend.invite_poller --dry-run   (show what would send)

Two targets (either or both, chosen by environment):
- ATS mode (primary): ATS_LIST_ID points at the "Application Tracking System"
  list (folder AI Recruitment). One task per applicant; the candidate phone is
  read from the structured "Phone no." / "Phone Number" custom fields and the
  role from "Role" / "Interview Profile" / "Which Profile are you applying
  for?" fields. Task name is the candidate name.
- Folder mode (legacy): CLICKUP_CANDIDATE_FOLDER_ID points at the
  "Teamrecrut — Candidate" folder. Phone is parsed from the Profile task
  description; setting Yes on the Profile task invites for every application.

Design rules:
- One invite per task per Yes. Flip No then Yes to re-send.
- Send failures retry on every cycle while the field stays Yes, and are
  reported as a ClickUp task comment only when the outcome changes (no
  comment spam on repeated identical failures). Success always comments.
- Missing Chatwoot configuration is reported per task, never crashes cron.

Environment: CLICKUP_API_TOKEN, CHATWOOT_URL, CHATWOOT_TOKEN,
CHATWOOT_ACCOUNT_ID, CHATWOOT_INBOX_ID, ATS_LIST_ID (ATS list),
CLICKUP_CANDIDATE_FOLDER_ID (legacy folder mode),
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
ATS_LIST_ENV = 'ATS_LIST_ID'
FOLDER_ENV = 'CLICKUP_CANDIDATE_FOLDER_ID'
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

# ATS custom-field names (Application Tracking System list).
ATS_PHONE_FIELDS = ('Phone no.', 'Phone Number')
ATS_ROLE_FIELD = 'Role'
ATS_PROFILE_FIELD = 'Interview Profile'
ATS_LABELS_FIELD = 'Which Profile are you applying for?'


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
    digits = re.sub(r'\D', '', str(raw or ''))
    # Indian mobile numbers captured with a stray leading zero (e.g. 09908…).
    if len(digits) == 11 and digits.startswith('0'):
        digits = digits[1:]
    if len(digits) == 10:
        return '+91' + digits
    if len(digits) == 12 and digits.startswith('91'):
        return '+' + digits
    if digits:
        return '+' + digits.lstrip('0')
    return ''


def _mask(phone):
    return phone[:-4] + '****' if len(phone) > 4 else '****'


def _yes_selected(field, yes_option_id):
    """ClickUp task reads return the selected option's orderindex (int) or,
    on some builds, the option id (str). Handle both; None means unset."""
    if not field:
        return False
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


def _invite_selected(task, field):
    """field is the cached state dict {fid, yes, no}, not the raw task field."""
    if not field:
        return False
    return _yes_selected(_invite_field(task, field['fid']), field['yes'])


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


def _list_tasks(cu, lid, extra='', max_pages=50):
    tasks, page = [], 0
    while page < max_pages:
        res = cu.call('GET', f'list/{lid}/task?include_closed=true&page={page}&subtasks=false{extra}')
        batch = res.get('tasks') or []
        tasks.extend(batch)
        if len(batch) < 100 or res.get('last_page') is True:
            break
        page += 1
    return tasks


def _list_tasks_filtered(cu, lid, field_id, value):
    """Server-side filtered task query: only tasks whose custom field equals
    value. Keeps the poll cycle tiny on 1000+-task lists."""
    import urllib.parse
    q = urllib.parse.quote(json.dumps([{'field_id': field_id, 'operator': '=', 'value': value}]))
    return _list_tasks(cu, lid, f'&custom_fields={q}')


def _comment(cu, task_id, text):
    cu.call('POST', f'task/{task_id}/comment', {'comment_text': text})


# ─── shared per-task delivery ─────────────────────────────────────────────────
def _deliver(cu, cw, state, tid, name, role, phone, actions, log, dry):
    """Send one invite (or simulate). Caller has already verified the trigger
    and that this task was not already sent for this Yes."""
    entry = state['tasks'].setdefault(tid, {})
    label = f'{name} · {role}'
    if dry:
        actions.append(f'WOULD SEND invite to {label}')
        return
    entry['saw_yes'] = True
    try:
        if not cw.configured():
            raise PollerError('Chatwoot is not configured '
                              '(CHATWOOT_TOKEN / CHATWOOT_INBOX_ID missing).')
        if not phone:
            raise PollerError('No phone number found on this task.')
        text = INVITE_TEXT.format(name=str(name).split(' ')[0], role=role, link=INVITE_LINK)
        conv = cw.send_whatsapp(phone, str(name), text)
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


def _already_sent(state, tid):
    entry = state['tasks'].get(tid) or {}
    return entry.get('saw_yes') and entry.get('status') == 'sent'


def _reset_if_deselected(state, tid, selected):
    if not selected:
        entry = state['tasks'].get(tid)
        if entry and entry.get('saw_yes'):
            entry['saw_yes'] = False  # observed No/unset: a later Yes re-sends


# ─── ATS mode: one task per applicant, structured fields ──────────────────────
def _ats_context(cu, lid):
    """Field definitions of the ATS list needed to read phone and role."""
    ctx = {'phone_fids': [], 'role': {}, 'profile': {}, 'labels': {}}
    for f in cu.call('GET', f'list/{lid}/field').get('fields') or []:
        name = f.get('name', '')
        options = (f.get('type_config') or {}).get('options') or []
        if name in ATS_PHONE_FIELDS:
            ctx['phone_fids'].append(f['id'])
        elif name == ATS_ROLE_FIELD:
            ctx['role'] = {o.get('orderindex'): o.get('name') for o in options}
        elif name == ATS_PROFILE_FIELD:
            ctx['profile'] = {o.get('orderindex'): str(o.get('name') or '').strip() for o in options}
        elif name == ATS_LABELS_FIELD:
            ctx['labels'] = {o.get('id'): str(o.get('name') or '').strip() for o in options}
    return ctx


def _ats_phone(task, ctx):
    for fid in ctx['phone_fids']:
        for f in task.get('custom_fields') or []:
            if f.get('id') == fid and f.get('value'):
                return _normalize_phone(f['value'])
    return ''


def _ats_role(task, ctx):
    for f in task.get('custom_fields') or []:
        name = f.get('name', '')
        value = f.get('value')
        if value is None:
            continue
        if name == ATS_ROLE_FIELD:
            mapped = ctx['role'].get(value)
            if mapped:
                return mapped.strip()
        elif name == ATS_PROFILE_FIELD:
            mapped = ctx['profile'].get(value)
            if mapped:
                return mapped
        elif name == ATS_LABELS_FIELD and isinstance(value, list):
            names = [ctx['labels'].get(v) for v in value]
            names = [n for n in names if n]
            if names:
                return ' / '.join(names[:2])
    return 'the role you applied for'


def _ats_has_profile(task, ctx):
    """True when the task's Interview Profile (or role fallbacks) is set."""
    for f in task.get('custom_fields') or []:
        name = f.get('name', '')
        value = f.get('value')
        if value is None or value == '':
            continue
        if name in (ATS_ROLE_FIELD, ATS_PROFILE_FIELD, ATS_LABELS_FIELD):
            if isinstance(value, list) and not value:
                continue
            return True
    return False


def _default_invite_for_profiled(cu, cw, state, task, field, ctx, dry):
    """Once Interview Profile is selected, Interview Invite never stays empty:
    default it to No via the API (ClickUp has no conditional visibility and
    the default cannot be set on an existing field)."""
    if not field.get('no'):
        return
    current = _invite_field(task, field['fid'])
    if current is not None and current.get('value') is not None:
        return  # already carries a value
    if not _ats_has_profile(task, ctx):
        return  # not yet profiled: leave unset until a profile is chosen
    if dry:
        return
    try:
        cu.call('POST', f"task/{task['id']}/field/{field['fid']}", {'value': field['no']})
    except PollerError:
        pass  # best-effort housekeeping; the invite flow itself is unaffected


def _poll_ats_list(cu, cw, state, lid, actions, log, dry):
    field = ensure_invite_field(cu, lid, state)
    ctx = _ats_context(cu, lid)
    # Server-side filter keeps cycles tiny on 1000+-task lists (free-tier
    # rate limits made full scans time out a 2-minute cron window).
    yes_tasks = _list_tasks_filtered(cu, lid, field['fid'], field['yes'])
    for task in yes_tasks:
        tid = task['id']
        name = (task.get('name') or 'Candidate').strip()
        selected = _invite_selected(task, field)
        _reset_if_deselected(state, tid, selected)
        if not selected or _already_sent(state, tid):
            continue
        phone = _ats_phone(task, ctx)
        role = _ats_role(task, ctx)
        _deliver(cu, cw, state, tid, name, role, phone, actions, log, dry)
    # Send loop above only sees Yes tasks; a No→Yes re-send needs to observe
    # the No in between. State-tracked tasks (previously sent) are few, so
    # probe them individually instead of scanning the whole list.
    current_yes = {t['id'] for t in yes_tasks}
    for tid, entry in list(state['tasks'].items()):
        if not entry.get('saw_yes') or tid in current_yes:
            continue
        try:
            task = cu.call('GET', f'task/{tid}')
        except PollerError:
            continue
        if not _invite_selected(task, field):
            entry['saw_yes'] = False  # observed No/unset: a later Yes re-sends
    # Housekeeping: default empty Interview Invite to No, but only on the
    # newest tasks (order_by=created desc, 2 pages max). New applicants land
    # here; the 1500-task historical backfill is already done.
    recent = _list_tasks(cu, lid, '&order_by=created&reverse=true', max_pages=2)
    for task in recent[:200]:
        _default_invite_for_profiled(cu, cw, state, task, field, ctx, dry)


# ─── folder mode (legacy Teamrecrut — Candidate): one List per candidate ─────
def _parse_interview(task):
    text = task.get('text_content') or ''
    name = (re.search(RE_NAME, text) or [None, task.get('name', 'Candidate')])[1].strip()
    role = (re.search(RE_ROLE, text) or [None, 'the role'])[1].strip()
    return {'name': name, 'role': role}


def _profile_phone(tasks):
    for t in tasks:
        if t.get('name', '').startswith('Candidate Profile'):
            m = re.search(RE_PHONE, t.get('text_content') or '')
            if m:
                return _normalize_phone(m.group(1))
    return ''


def _poll_folder(cu, cw, state, folder, actions, log, dry):
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
        profile_yes = any(_invite_selected(t, field) for t in profile)
        for task in interviews:
            tid = task['id']
            selected = _invite_selected(task, field)
            trigger = selected or profile_yes
            _reset_if_deselected(state, tid, trigger)
            if not trigger or _already_sent(state, tid):
                continue
            info = _parse_interview(task)
            _deliver(cu, cw, state, tid, info['name'], info['role'], phone, actions, log, dry)


# ─── the poll cycle ───────────────────────────────────────────────────────────
def run_once(cu, cw, state, folder=None, ats_list=None, dry=False, log=None):
    """Poll configured targets; send invites for tasks marked Yes.

    Returns a list of human-readable action lines (empty when nothing to do).
    """
    log = log or (lambda msg: None)
    actions = []
    if not cu.configured():
        raise PollerError('ClickUp is not configured; set CLICKUP_API_TOKEN.')
    if ats_list:
        _poll_ats_list(cu, cw, state, ats_list, actions, log, dry)
    if folder:
        _poll_folder(cu, cw, state, folder, actions, log, dry)
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
    ats_list = os.getenv(ATS_LIST_ENV, '').strip() or None
    folder = os.getenv(FOLDER_ENV, '').strip() or None
    if not ats_list and not folder:
        print(f'Set {ATS_LIST_ENV} or {FOLDER_ENV}.', file=sys.stderr)
        return 2
    while True:
        state = load_state(state_path)
        try:
            actions = run_once(cu, cw, state, folder=folder, ats_list=ats_list, dry=dry)
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
