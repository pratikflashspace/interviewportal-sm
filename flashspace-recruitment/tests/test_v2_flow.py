import copy
import unittest
from backend.v2_flow import create_flow,commit_answer,resolve_next,FlowError,public_flow

class FlowTests(unittest.TestCase):
    def run_flow(self,bank='sales',followup=None):
        f=create_flow(bank,10)
        while f['status']!='completed':
            f,_=commit_answer(f,'event-'+str(len(f['answers'])),f['version'],f['active']['id'],'A fictional answer.','test-time')
            f=resolve_next(f,followup)
        return f
    def test_counts_and_order(self):
        for bank in ('sales','operations','marketing'):
            f=self.run_flow(bank)
            self.assertEqual(len(f['answers']),10)
            self.assertEqual([a['stage'] for a in f['answers']],['generic']*6+['domain']*4)
            self.assertEqual([a['category'] for a in f['answers'][-4:]],['fundamental']*2+['scenario']*2)
    def test_followup_budget_and_parent(self):
        f=self.run_flow(followup=0)
        self.assertLessEqual(len(f['answers']),14)
        self.assertEqual(f['followups'],{'generic':2,'domain':2})
        for n,a in enumerate(f['answers']):
            if a['kind']=='followup':self.assertEqual(a['parent_id'],f['answers'][n-1]['question_id'])
    def test_selection_pinned_and_role_specific(self):
        a=create_flow('sales',1);b=create_flow('sales',1);c=create_flow('operations',1)
        self.assertEqual(a,b)
        self.assertTrue(all(q['id'].startswith('sales') for q in a['selected'][6:]))
        self.assertTrue(all(q['id'].startswith('operations') for q in c['selected'][6:]))
        self.assertEqual(len({q['id'] for q in a['selected']}),10)
        self.assertNotIn('selected',public_flow(a))
        self.assertNotIn('followups',public_flow(a)['active'])
    def test_event_replay_does_not_add_answer(self):
        f=create_flow('sales',1);q=f['active']['id']
        f,fresh=commit_answer(f,'unique-event',0,q,'Answer.','test')
        self.assertTrue(fresh)
        again,fresh=commit_answer(f,'unique-event',0,q,'Answer.','test')
        self.assertFalse(fresh);self.assertEqual(f,again)
        with self.assertRaises(FlowError):commit_answer(f,'unique-event',0,q,'Different','test')
    def test_stale_and_unknown_bank_rejected(self):
        with self.assertRaises(FlowError):create_flow('guessed',1)
        f=create_flow('sales',1)
        for version,q in [(9,f['active']['id']),(False,f['active']['id']),(0,'wrong')]:
            with self.assertRaises(FlowError):commit_answer(f,'event-test',version,q,'Answer','test')
    def test_pending_answer_recovery_skips_optional_inference(self):
        f=create_flow('sales',1)
        f,_=commit_answer(f,'unique-event',0,f['active']['id'],'Answer','test')
        saved=copy.deepcopy(f);recovered=resolve_next(saved)
        self.assertEqual(len(recovered['answers']),1)
        self.assertEqual(recovered['active']['id'],'generic-2')
        self.assertEqual(resolve_next(recovered),recovered)
