"""Tests for the ClickUp Interview Invite → WhatsApp (Chatwoot) poller.

Covers both targets: ATS mode (one task per applicant, structured custom
fields) and legacy folder mode (Teamrecrut — Candidate, one List per
candidate, description parsing).
"""
import json
import os
import tempfile
import unittest

import backend.invite_poller as ip


class FakeCU:
    """ClickUp fake with lists/tasks/fields/comments and dropdown semantics."""

    def __init__(self):
        self.token = 'tok'
        self.lists = {}   # lid -> {'name':..., 'tasks': {tid: task}}
        self.fields = {}  # lid -> {fid: field def}
        self.values = {}  # (tid, fid) -> option id
        self.comments = {}  # tid -> [texts]

    def configured(self):
        return True

    def call(self, method, path, data=None):
        if method == 'GET' and path.startswith('folder/') and path.endswith('/list?archived=false'):
            return {'lists': [{'id': lid, 'name': l['name']} for lid, l in self.lists.items()]}
        if method == 'GET' and path.endswith('/field'):
            lid = path.split('/')[1]
            return {'fields': list(self.fields.get(lid, {}).values())}
        if method == 'POST' and path.endswith('/field'):
            lid = path.split('/')[1]
            fid = f'fld-{lid}-{len(self.fields.get(lid, {}))}'
            opts = [{'id': f'opt-{i}', 'name': o['name'], 'orderindex': i}
                    for i, o in enumerate((data.get('type_config') or {}).get('options') or [])]
            if not opts:
                opts = [{'id': 'yes-id', 'name': 'Yes', 'orderindex': 0},
                        {'id': 'no-id', 'name': 'No', 'orderindex': 1}]
            elif [o['name'] for o in opts] == ['Yes', 'No']:
                # keep the classic ids tests rely on
                opts = [{'id': 'yes-id', 'name': 'Yes', 'orderindex': 0},
                        {'id': 'no-id', 'name': 'No', 'orderindex': 1}]
            field = {'id': fid, 'name': data['name'], 'type': data['type'],
                     'type_config': {'options': opts}}
            self.fields.setdefault(lid, {})[fid] = field
            return {'field': field}
        if method == 'GET' and '/task?' in path:
            lid = path.split('/')[1]
            query = path.split('?', 1)[1]
            out = []
            all_tasks = list(self.lists[lid]['tasks'].items())
            # server-side custom_fields filter: [{field_id, operator: =, value}]
            import urllib.parse as up
            params = dict(p.split('=', 1) for p in query.split('&') if '=' in p)
            if 'custom_fields' in params:
                flt = json.loads(up.unquote(params['custom_fields']))
                want_fid, want_val = flt[0]['field_id'], flt[0]['value']
                matched = {tid for (tid, fid), v in self.values.items()
                           if fid == want_fid and v == want_val}
                all_tasks = [(tid, t) for tid, t in all_tasks if tid in matched]
            if params.get('order_by') == 'created' and params.get('reverse') == 'true':
                all_tasks = list(reversed(all_tasks))
            for tid, t in all_tasks:
                cf = []
                for (ttid, fid), opt in self.values.items():
                    if ttid == tid and fid in self.fields.get(lid, {}):
                        cf.append({'id': fid, 'name': self.fields[lid][fid]['name'],
                                   'type_config': self.fields[lid][fid]['type_config'], 'value': opt})
                # allow tasks to carry pre-built custom_fields (ATS-style)
                for extra in t.get('custom_fields', []):
                    if not any(c['id'] == extra['id'] for c in cf):
                        cf.append(extra)
                out.append({'id': tid, 'name': t['name'], 'text_content': t.get('text_content', ''),
                            'custom_fields': cf})
            return {'tasks': out}
        if method == 'POST' and '/comment' in path:
            tid = path.split('/')[1]
            self.comments.setdefault(tid, []).append(data['comment_text'])
            return {'id': 1}
        if method == 'GET' and path.startswith('task/') and '/comment' not in path and '?' not in path:
            tid = path.split('/')[1]
            for lid, l in self.lists.items():
                if tid in l['tasks']:
                    cf = []
                    for (ttid, fid), opt in self.values.items():
                        if ttid == tid and fid in self.fields.get(lid, {}):
                            cf.append({'id': fid, 'name': self.fields[lid][fid]['name'],
                                       'type_config': self.fields[lid][fid]['type_config'], 'value': opt})
                    for extra in l['tasks'][tid].get('custom_fields', []):
                        if not any(c['id'] == extra['id'] for c in cf):
                            cf.append(extra)
                    return {'id': tid, 'name': l['tasks'][tid]['name'],
                            'text_content': l['tasks'][tid].get('text_content', ''),
                            'custom_fields': cf}
            raise AssertionError(f'unknown task: {tid}')
        if method == 'POST' and path.startswith('task/') and '/field/' in path:
            tid = path.split('/')[1]; fid = path.split('/')[3]
            self.values[(tid, fid)] = (data or {}).get('value')
            return {}
        raise AssertionError(f'unmapped call: {method} {path}')

    def set_field(self, tid, fid, value, lid='l1'):
        """Test helper: set a raw custom-field value on a task."""
        self.values[(tid, fid)] = value


class FakeCW:
    def __init__(self, fail=False, deliver_status='sent'):
        self.token, self.inbox = 'tok', '19'
        self.sent = []
        self.fail = fail
        self.deliver_status = deliver_status
        self._counter = 100

    def configured(self):
        return True

    def send_whatsapp(self, phone, name, text, template_vars=None):
        if self.fail:
            raise ip.PollerError('Chatwoot 500 on POST conversations/1/messages')
        self._counter += 1
        self.sent.append({'phone': phone, 'name': name, 'text': text,
                          'template_vars': template_vars, 'message_id': self._counter})
        return 7, self._counter

    def message_status(self, conversation_id, message_id):
        return self.deliver_status

    def sync_templates(self):
        self.synced = True


def make_lists(cu, phone='+919876543210'):
    cu.lists['l1'] = {'name': 'Test Candidate · FS-00000001', 'tasks': {
        'p1': {'name': 'Candidate Profile — Test Candidate · FS-00000001',
               'text_content': f'TEAMRECRUT CANDIDATE PROFILE\nCandidate: Test Candidate\nEmail: t@x.dev\nPhone: {phone}\n'},
        'i1': {'name': 'Candidate Interview summary and transcript — Sales · FS-abcdefgh',
               'text_content': 'Application reference: FS-abcdefgh (abc)\nCandidate: Test Candidate\nRole: Sales\n'},
        'i2': {'name': 'Candidate Interview summary and transcript — Ops · FS-stuvwxyz',
               'text_content': 'Application reference: FS-stuvwxyz (stu)\nCandidate: Test Candidate\nRole: Operations\n'},
    }}


def make_ats(cu):
    """ATS-style list: one task per applicant with structured fields."""
    cu.lists['ats'] = {'name': 'Application Tracking System', 'tasks': {
        'a1': {'name': 'Shivam Dubey', 'custom_fields': [
            {'id': 'f-phone', 'name': 'Phone no.', 'type': 'short_text', 'value': '9289444912'},
            {'id': 'f-role', 'name': 'Role', 'type': 'drop_down', 'value': 3,
             'type_config': {'options': [{'id': 'r0', 'name': 'EIR', 'orderindex': 0},
                                         {'id': 'r1', 'name': 'BD', 'orderindex': 1},
                                         {'id': 'r2', 'name': 'FO', 'orderindex': 2},
                                         {'id': 'r3', 'name': 'Generalist', 'orderindex': 3}]}},
        ]},
        'a2': {'name': 'Abhishek Gupta', 'custom_fields': [
            {'id': 'f-phone2', 'name': 'Phone Number', 'type': 'short_text', 'value': '09908415266'},
            {'id': 'f-prof', 'name': 'Interview Profile', 'type': 'drop_down', 'value': 2,
             'type_config': {'options': [{'id': 'p0', 'name': 'Human Resources', 'orderindex': 0},
                                         {'id': 'p1', 'name': 'Operations', 'orderindex': 1},
                                         {'id': 'p2', 'name': 'Sales ', 'orderindex': 2}]}},
        ]},
        'a3': {'name': 'No Data', 'custom_fields': []},
    }}
    # ATS list also has the phone/role defs as list fields for _ats_context
    cu.fields['ats'] = {
        'f-phone': {'id': 'f-phone', 'name': 'Phone no.', 'type': 'short_text', 'type_config': {}},
        'f-phone2': {'id': 'f-phone2', 'name': 'Phone Number', 'type': 'short_text', 'type_config': {}},
        'f-role': {'id': 'f-role', 'name': 'Role', 'type': 'drop_down',
                   'type_config': {'options': [{'id': 'r0', 'name': 'EIR', 'orderindex': 0},
                                               {'id': 'r1', 'name': 'BD', 'orderindex': 1},
                                               {'id': 'r2', 'name': 'FO', 'orderindex': 2},
                                               {'id': 'r3', 'name': 'Generalist', 'orderindex': 3}]}},
        'f-prof': {'id': 'f-prof', 'name': 'Interview Profile', 'type': 'drop_down',
                   'type_config': {'options': [{'id': 'p0', 'name': 'Human Resources', 'orderindex': 0},
                                               {'id': 'p1', 'name': 'Operations', 'orderindex': 1},
                                               {'id': 'p2', 'name': 'Sales ', 'orderindex': 2}]}},
    }


class FolderModeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.state_path = os.path.join(self.tmp, 'state.json')
        self.cu = FakeCU()
        self.cw = FakeCW()
        make_lists(self.cu)

    def run_cycle(self):
        state = ip.load_state(self.state_path)
        actions = ip.run_once(self.cu, self.cw, state, folder='f1', dry=False)
        ip.save_state(self.state_path, state)
        return actions

    def set_invite(self, tid, value):
        state = ip.load_state(self.state_path)
        fld = ip.ensure_invite_field(self.cu, 'l1', state)
        ip.save_state(self.state_path, state)
        if value is None:
            self.cu.values.pop((tid, fld['fid']), None)
        else:
            self.cu.values[(tid, fld['fid'])] = value

    def test_creates_dropdown_and_sends_for_interview_yes(self):
        self.set_invite('i1', 'yes-id')
        actions = self.run_cycle()
        self.assertEqual(len(self.cw.sent), 1)
        s = self.cw.sent[0]
        self.assertEqual(s['phone'], '+919876543210')
        self.assertEqual(s['name'], 'Test Candidate')
        self.assertIn('shortlisted for Sales', s['text'])
        self.assertIn('https://recrut.teamlens.co/', s['text'])
        # template mode: 5 single-line variables for the approved Meta template
        self.assertEqual(s['template_vars']['candidate_name'], 'Test')
        self.assertEqual(s['template_vars']['role'], 'Sales')
        self.assertEqual(s['template_vars']['site_link'], 'https://recrut.teamlens.co/')
        self.assertTrue(getattr(self.cw, 'synced', False), 'sync_templates must run per cycle')
        self.assertTrue(actions and actions[0].startswith('SENT'))
        self.assertIn('Interview invite sent on WhatsApp', self.cu.comments['i1'][0])

    def test_profile_yes_invites_all_roles(self):
        self.set_invite('p1', 'yes-id')
        actions = self.run_cycle()
        self.assertEqual(len(self.cw.sent), 2)
        roles = [s['text'] for s in self.cw.sent]
        self.assertTrue(any('shortlisted for Sales' in r for r in roles))
        self.assertTrue(any('shortlisted for Operations' in r for r in roles))

    def test_second_cycle_does_not_resend(self):
        self.set_invite('i1', 'yes-id')
        self.run_cycle()
        actions2 = self.run_cycle()
        self.assertEqual(len(self.cw.sent), 1)
        self.assertEqual(actions2, [])

    def test_no_then_yes_resends(self):
        self.set_invite('i1', 'yes-id')
        self.run_cycle()
        self.set_invite('i1', 'no-id')
        self.assertEqual(self.run_cycle(), [])
        self.set_invite('i1', 'yes-id')
        self.run_cycle()
        self.assertEqual(len(self.cw.sent), 2)

    def test_missing_phone_reports_and_no_send(self):
        self.cu.lists['l1']['tasks']['p1']['text_content'] = 'TEAMRECRUT CANDIDATE PROFILE\nCandidate: Test Candidate\n'
        self.set_invite('i1', 'yes-id')
        actions = self.run_cycle()
        self.assertEqual(self.cw.sent, [])
        self.assertTrue(any('FAILED' in a for a in actions))
        self.assertTrue(any('No phone number' in c for c in self.cu.comments['i1']))
        # Identical failure the next cycle is retried but NOT re-commented/re-reported
        self.assertEqual(self.run_cycle(), [])
        self.assertEqual(len(self.cu.comments['i1']), 1)

    def test_chatwoot_failure_comments_once_not_spam(self):
        self.cw = FakeCW(fail=True)
        self.set_invite('i1', 'yes-id')
        a1 = self.run_cycle()
        a2 = self.run_cycle()
        self.assertEqual(self.cw.sent, [])
        self.assertEqual(len(self.cu.comments['i1']), 1)
        self.assertTrue(any('FAILED' in a for a in a1))
        self.assertEqual(a2, [])

    def test_unset_yes_tracks_reset(self):
        self.set_invite('i1', 'yes-id')
        self.run_cycle()
        self.set_invite('i1', None)
        self.assertEqual(self.run_cycle(), [])
        self.set_invite('i1', 'yes-id')
        self.run_cycle()
        self.assertEqual(len(self.cw.sent), 2)

    def test_dry_run_sends_nothing(self):
        self.set_invite('i1', 'yes-id')
        state = ip.load_state(self.state_path)
        actions = ip.run_once(self.cu, self.cw, state, folder='f1', dry=True)
        ip.save_state(self.state_path, state)
        self.assertEqual(self.cw.sent, [])
        self.assertTrue(actions and actions[0].startswith('WOULD SEND'))


class ATSModeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.state_path = os.path.join(self.tmp, 'state.json')
        self.cu = FakeCU()
        self.cw = FakeCW()
        make_ats(self.cu)

    def run_cycle(self):
        state = ip.load_state(self.state_path)
        actions = ip.run_once(self.cu, self.cw, state, ats_list='ats', dry=False)
        ip.save_state(self.state_path, state)
        return actions

    def set_invite(self, tid, value):
        state = ip.load_state(self.state_path)
        fld = ip.ensure_invite_field(self.cu, 'ats', state)
        ip.save_state(self.state_path, state)
        if value is None:
            self.cu.values.pop((tid, fld['fid']), None)
        else:
            self.cu.values[(tid, fld['fid'])] = value

    def test_ats_sends_from_structured_fields(self):
        self.set_invite('a1', 'yes-id')
        actions = self.run_cycle()
        self.assertEqual(len(self.cw.sent), 1)
        s = self.cw.sent[0]
        self.assertEqual(s['phone'], '+919289444912')      # from Phone no. field
        self.assertEqual(s['name'], 'Shivam Dubey')        # task name
        self.assertIn('shortlisted for Generalist', s['text'])  # Role dropdown resolved
        self.assertEqual(s['template_vars']['role'], 'Generalist')
        self.assertTrue(actions and actions[0].startswith('SENT'))
        self.assertIn('Interview invite sent on WhatsApp', self.cu.comments['a1'][0])

    def test_ats_leading_zero_phone_and_profile_role(self):
        self.set_invite('a2', 'yes-id')
        self.run_cycle()
        s = self.cw.sent[0]
        self.assertEqual(s['phone'], '+919908415266')       # 09908… normalized
        self.assertIn('shortlisted for Sales', s['text'])  # Interview Profile option, trailing space stripped

    def test_ats_missing_data_fails_gracefully(self):
        self.set_invite('a3', 'yes-id')
        actions = self.run_cycle()
        self.assertEqual(self.cw.sent, [])
        self.assertTrue(any('FAILED' in a for a in actions))
        self.assertTrue(any('No phone number' in c for c in self.cu.comments['a3']))

    def test_ats_idempotent_per_task(self):
        self.set_invite('a1', 'yes-id')
        self.run_cycle()
        self.assertEqual(self.run_cycle(), [])
        self.assertEqual(len(self.cw.sent), 1)

    def test_ats_no_then_yes_resends(self):
        self.set_invite('a1', 'yes-id')
        self.run_cycle()
        self.set_invite('a1', 'no-id')
        self.assertEqual(self.run_cycle(), [])
        self.set_invite('a1', 'yes-id')
        self.run_cycle()
        self.assertEqual(len(self.cw.sent), 2)

    def test_ats_dry_run(self):
        self.set_invite('a1', 'yes-id')
        state = ip.load_state(self.state_path)
        actions = ip.run_once(self.cu, self.cw, state, ats_list='ats', dry=True)
        ip.save_state(self.state_path, state)
        self.assertEqual(self.cw.sent, [])
        self.assertTrue(any('WOULD SEND' in a for a in actions))

    def test_profiled_tasks_get_invite_defaulted_to_no(self):
        # a1 has Role set (Generalist) but no Interview Invite value yet.
        state = ip.load_state(self.state_path)
        fld = ip.ensure_invite_field(self.cu, 'ats', state)
        ip.save_state(self.state_path, state)
        self.assertNotIn(('a1', fld['fid']), self.cu.values)  # empty right now
        ip.run_once(self.cu, self.cw, state, ats_list='ats', dry=False)
        # poller must have written the "No" option id onto a1
        self.assertEqual(self.cu.values.get(('a1', fld['fid'])), 'no-id')
        # nothing was sent: value is No, not Yes
        self.assertEqual(self.cw.sent, [])

    def test_delivery_failure_posts_no_success_comment(self):
        # The bug found live: Chatwoot queues the message, then WhatsApp fails
        # (invalid template). The poller must NOT post a success comment.
        self.cw = FakeCW(deliver_status='failed')
        self.set_invite('a1', 'yes-id')
        actions = self.run_cycle()
        self.assertEqual(self.cw.sent and self.cw.sent[0]['template_vars'] is not None, True)
        self.assertTrue(any('FAILED' in a for a in actions))
        comments = self.cu.comments.get('a1', [])
        self.assertTrue(any('FAILED to deliver' in c for c in comments))
        self.assertFalse(any('invite sent on WhatsApp' in c for c in comments))
        # state must not latch 'sent' so the next cycle retries
        state = ip.load_state(self.state_path)
        self.assertNotEqual(state['tasks'].get('a1', {}).get('status'), 'sent')

    def test_gave_up_task_does_not_send_again_while_yes(self):
        # 2026-09-23 incident regression: an undeliverable number received a
        # fresh send attempt every cycle for ~18 hours (364 attempts). Once
        # the poller gives up after 3 retries, the task must stay terminal
        # while the field remains Yes; only a manual No->Yes re-arms it.
        self.cw = FakeCW(deliver_status='failed')
        self.set_invite('a1', 'yes-id')
        for _ in range(4):  # cycle 1-3 retry; cycle 4 sends then gives up
            self.run_cycle()
        self.assertEqual(len(self.cw.sent), 4)
        state = ip.load_state(self.state_path)
        self.assertTrue(state['tasks']['a1']['status'].startswith('failed (gave up'))
        # more cycles: still no further sends — the OLD bug sent one per cycle
        self.run_cycle(); self.run_cycle(); self.run_cycle()
        self.assertEqual(len(self.cw.sent), 4)
        # No->Yes re-arm still works: reset via deselect, then send once more
        self.set_invite('a1', None)
        self.run_cycle()
        self.set_invite('a1', 'yes-id')
        self.run_cycle()
        self.assertEqual(len(self.cw.sent), 5)

    def test_unprofiled_tasks_stay_empty(self):
        # a3 has no role/profile/labels at all: field stays untouched.
        state = ip.load_state(self.state_path)
        fld = ip.ensure_invite_field(self.cu, 'ats', state)
        ip.save_state(self.state_path, state)
        ip.run_once(self.cu, self.cw, state, ats_list='ats', dry=False)
        self.assertNotIn(('a3', fld['fid']), self.cu.values)

    def _delivery_field_value(self, tid):
        state = ip.load_state(self.state_path)
        delivery = ip.ensure_delivery_field(self.cu, 'ats', state)
        return self.cu.values.get((tid, delivery['fid']))

    def test_send_sets_delivery_field_and_refresh_upgrades_it(self):
        # Fresh send: field goes Pending then Sent; later cycles upgrade the
        # status in ClickUp as Chatwoot reports the real delivery state.
        self.cw = FakeCW(deliver_status='sent')
        self.set_invite('a1', 'yes-id')
        self.run_cycle()
        state = ip.load_state(self.state_path)
        delivery = ip.ensure_delivery_field(self.cu, 'ats', state)
        sent_opt = delivery['ids']['Sent']
        self.assertEqual(self.cu.values.get(('a1', delivery['fid'])), sent_opt)
        # message tracked for re-checks
        entry = state['tasks']['a1']
        self.assertEqual(entry.get('conv'), 7)
        self.assertTrue(entry.get('message_id'))
        self.assertFalse(entry.get('delivery_done'))
        # phone confirms delivery on a later cycle
        self.cw.deliver_status = 'delivered'
        self.run_cycle()
        self.assertEqual(self._delivery_field_value('a1'), delivery['ids']['Delivered'])
        # terminal: no further re-checks
        state = ip.load_state(self.state_path)
        self.assertTrue(state['tasks']['a1'].get('delivery_done'))

    def test_late_failure_flips_field_to_failed_and_comments(self):
        self.cw = FakeCW(deliver_status='sent')
        self.set_invite('a1', 'yes-id')
        self.run_cycle()
        # Meta rejects it after acceptance (the 131049 quality-filter case)
        self.cw.deliver_status = 'failed'
        actions = self.run_cycle()
        self.assertTrue(any('DELIVERY FAILED' in a for a in actions))
        self.assertEqual(self._delivery_field_value('a1'),
                         ip.ensure_delivery_field(self.cu, 'ats', ip.load_state(self.state_path))['ids']['Failed'])
        self.assertTrue(any('FAILED' in c for c in self.cu.comments.get('a1', [])))

    def test_read_is_terminal_and_tracked(self):
        self.cw = FakeCW(deliver_status='read')
        self.set_invite('a1', 'yes-id')
        self.run_cycle()
        state = ip.load_state(self.state_path)
        delivery = ip.ensure_delivery_field(self.cu, 'ats', state)
        self.assertEqual(self.cu.values.get(('a1', delivery['fid'])), delivery['ids']['Read'])
        self.assertTrue(state['tasks']['a1'].get('delivery_done'))

    def test_delivery_field_broken_does_not_stop_sends(self):
        # A malformed WhatsApp Delivery field (missing options) must never
        # block the invite sends themselves.
        cu = self.cu
        cu.fields['ats']['bad-delivery'] = {
            'id': 'bad-delivery', 'name': 'WhatsApp Delivery', 'type': 'drop_down',
            'type_config': {'options': [{'id': 'only', 'name': 'Bogus', 'orderindex': 0}]}}
        self.set_invite('a1', 'yes-id')
        actions = self.run_cycle()
        self.assertTrue(any('SENT' in a for a in actions))
        self.assertEqual(len(self.cw.sent), 1)


class SharedHelperTests(unittest.TestCase):
    def test_phone_normalization(self):
        self.assertEqual(ip._normalize_phone('98765 43210'), '+919876543210')
        self.assertEqual(ip._normalize_phone('+91 98765 43210'), '+919876543210')
        self.assertEqual(ip._normalize_phone('919876543210'), '+919876543210')
        self.assertEqual(ip._normalize_phone('09908415266'), '+919908415266')
        self.assertEqual(ip._normalize_phone(''), '')

    def test_yes_detection_both_value_shapes(self):
        field = {'id': 'f', 'value': 0, 'type_config': {'options': [
            {'id': 'yes-id', 'name': 'Yes', 'orderindex': 0},
            {'id': 'no-id', 'name': 'No', 'orderindex': 1}]}}
        self.assertTrue(ip._yes_selected(field, 'yes-id'))
        field['value'] = 'yes-id'
        self.assertTrue(ip._yes_selected(field, 'yes-id'))
        field['value'] = 1
        self.assertFalse(ip._yes_selected(field, 'yes-id'))
        field['value'] = None
        self.assertFalse(ip._yes_selected(field, 'yes-id'))

    def test_state_file_roundtrip(self):
        tmp = tempfile.mkdtemp()
        p = os.path.join(tmp, 's.json')
        state = {'fields': {'l1': {'fid': 'x', 'yes': 'y', 'no': 'n'}}, 'tasks': {}}
        ip.save_state(p, state)
        self.assertEqual(ip.load_state(p), state)


if __name__ == '__main__':
    unittest.main()
