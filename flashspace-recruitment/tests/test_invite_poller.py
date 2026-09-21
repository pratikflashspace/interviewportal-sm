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
            field = {'id': fid, 'name': data['name'], 'type': data['type'],
                     'type_config': {'options': [{'id': 'yes-id', 'name': 'Yes', 'orderindex': 0},
                                                 {'id': 'no-id', 'name': 'No', 'orderindex': 1}]}}
            self.fields.setdefault(lid, {})[fid] = field
            return {'field': field}
        if method == 'GET' and '/task?' in path:
            lid = path.split('/')[1]
            out = []
            for tid, t in self.lists[lid]['tasks'].items():
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
        raise AssertionError(f'unmapped call: {method} {path}')

    def set_field(self, tid, fid, value, lid='l1'):
        """Test helper: set a raw custom-field value on a task."""
        self.values[(tid, fid)] = value


class FakeCW:
    def __init__(self, fail=False):
        self.token, self.inbox = 'tok', '19'
        self.sent = []
        self.fail = fail

    def configured(self):
        return True

    def send_whatsapp(self, phone, name, text):
        if self.fail:
            raise ip.PollerError('Chatwoot 500 on POST conversations/1/messages')
        self.sent.append((phone, name, text))
        return 7


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
        phone, name, text = self.cw.sent[0]
        self.assertEqual(phone, '+919876543210')
        self.assertEqual(name, 'Test Candidate')
        self.assertIn('shortlisted for Sales', text)
        self.assertIn('https://recrut.teamlens.co/', text)
        self.assertTrue(actions and actions[0].startswith('SENT'))
        self.assertIn('Interview invite sent on WhatsApp', self.cu.comments['i1'][0])

    def test_profile_yes_invites_all_roles(self):
        self.set_invite('p1', 'yes-id')
        actions = self.run_cycle()
        self.assertEqual(len(self.cw.sent), 2)
        roles = [t for _, _, t in self.cw.sent]
        self.assertTrue(any('shortlisted for Sales' in t for t in roles))
        self.assertTrue(any('shortlisted for Operations' in t for t in roles))

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
        phone, name, text = self.cw.sent[0]
        self.assertEqual(phone, '+919289444912')      # from Phone no. field
        self.assertEqual(name, 'Shivam Dubey')        # task name
        self.assertIn('shortlisted for Generalist', text)  # Role dropdown resolved
        self.assertTrue(actions and actions[0].startswith('SENT'))
        self.assertIn('Interview invite sent on WhatsApp', self.cu.comments['a1'][0])

    def test_ats_leading_zero_phone_and_profile_role(self):
        self.set_invite('a2', 'yes-id')
        self.run_cycle()
        phone, name, text = self.cw.sent[0]
        self.assertEqual(phone, '+919908415266')       # 09908… normalized
        self.assertIn('shortlisted for Sales', text)  # Interview Profile option, trailing space stripped

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
