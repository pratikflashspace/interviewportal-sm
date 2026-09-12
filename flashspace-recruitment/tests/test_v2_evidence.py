import copy
import os
import unittest
from unittest.mock import patch
from backend.v2_endpoint import EvidenceOnlyAI
from backend.v2_server import CRITERIA
from backend.server import APIError

class EvidenceTests(unittest.TestCase):
    def setUp(self):
        self.env=patch.dict(os.environ,{'SARVAM_API_KEY':'synthetic-test-only'});self.env.start();self.addCleanup(self.env.stop)
        self.ai=EvidenceOnlyAI()
        self.answers=[{'flow_version':2,'question_id':'g1','stage':'generic','answer':'I organized a fictional project.'},
                      {'flow_version':2,'question_id':'d1','stage':'domain','answer':'I qualified fictional leads.'}]
        self.report={'summary':'These claims are unverified.','criteria':[{'name':name,'reason':'A claimed example.',
                    'evidence':self.answers[1 if i>=3 else 0]['answer'],'source_id':'d1' if i>=3 else 'g1','confidence':'medium'} for i,name in enumerate(CRITERIA)]}
    def test_no_unapproved_scores(self):
        with patch.object(self.ai.provider,'structured',return_value=copy.deepcopy(self.report)):
            result=self.ai.evaluate({'title':'Sales','details':'Test'},self.answers)
        self.assertIsNone(result['score']);self.assertTrue(result['human_review_required'])
        self.assertTrue(all('score' not in c for c in result['criteria']))
    def test_invented_quote_and_wrong_round_rejected(self):
        for field,value in [('evidence','I invented this.'),('source_id','d1')]:
            report=copy.deepcopy(self.report);report['criteria'][0][field]=value
            with patch.object(self.ai.provider,'structured',return_value=report):
                with self.assertRaises(APIError):self.ai.evaluate({'title':'Sales','details':'Test'},self.answers)
    def test_absent_evidence_has_low_confidence(self):
        report=copy.deepcopy(self.report);report['criteria'][0]['evidence']=''
        with patch.object(self.ai.provider,'structured',return_value=report):
            result=self.ai.evaluate({'title':'Sales','details':'Test'},self.answers)
        self.assertEqual(result['criteria'][0]['confidence'],'low');self.assertEqual(result['criteria'][0]['source_id'],'')
    def test_redirects_not_followed(self):
        from backend.v2_stream import connect
        error=RuntimeError('redirect')
        self.assertIs(connect.process_redirect(None,error),error)
