import unittest
from backend.v2_drafts import DraftStore
from backend.server import APIError
from test_v2_replay import ReplayTests

class DraftTests(ReplayTests):
    def test_draft_survives_recreation_without_submitting(self):
        path='/api/v2/applications/'+self.aid+'/draft'
        response=self.req(path,{'question_id':self.qid,'revision':0,'transcript':'A finalized draft.'})
        self.assertEqual(response['status'],200)
        self.assertEqual(DraftStore(self.app.store).get(self.aid,self.qid)['transcript'],'A finalized draft.')
        self.assertEqual(self.app.store.get(self.aid)['answers'],[])
        self.assertEqual(self.app.flow(self.aid)['version'],0)
    def test_stale_draft_and_wrong_question_rejected(self):
        path='/api/v2/applications/'+self.aid+'/draft'
        body={'question_id':self.qid,'revision':0,'transcript':'Draft one'}
        self.assertEqual(self.req(path,body)['status'],200)
        self.assertEqual(self.req(path,body)['status'],409)
        self.assertEqual(self.req(path,{**body,'revision':1,'question_id':'other'})['status'],409)
        self.assertEqual(self.req(path,{**body,'revision':1,'transcript':'Draft two'})['status'],200)
    def test_draft_private_and_bounded(self):
        path='/api/v2/applications/'+self.aid+'/draft'
        self.assertEqual(self.req(path,{'question_id':self.qid,'revision':0,'transcript':'a'*6001})['status'],400)
        self.register('other@example.com')
        self.assertEqual(self.req(path)['status'],404)
        self.assertEqual(self.req(path,{'question_id':self.qid,'revision':0,'transcript':'wrong owner'})['status'],404)
