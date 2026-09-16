"""Real WSGI + isolated database profile tests. No live provider or candidate data."""
import copy
import json
import os
import unittest
from concurrent.futures import ThreadPoolExecutor
from backend.candidate_profile import PATH, ENTRIES, TEXT, validate, handle
from backend.server import APIError
import test_workspace_server as fixtures
from test_workspace_postgres_journey import PostgresJourney

def entry(section,**values):
    value={k:'' for k in ENTRIES[section]}
    if section in ('education','experience'):value['current']=False
    value.update(values);return value

class ProfileTests(unittest.TestCase):
    setUp=fixtures.WorkspaceTests.setUp
    req=fixtures.WorkspaceTests.req
    signup=fixtures.WorkspaceTests.signup
    recruiter=fixtures.WorkspaceTests.recruiter
    login_recruiter=fixtures.WorkspaceTests.login_recruiter
    def get(self):
        result=self.req(PATH);self.assertEqual(result['status'],200,result);return result['body']
    def save(self,section,value,version=None):
        return self.req(PATH,{'version':self.get()['version'] if version is None else version,'section':section,'value':value})
    def test_persist_sections_and_preserve_original_text(self):
        self.signup();old='Original education\nNot converted or replaced.'
        start=self.req('/api/workspace/profile')['body']['version']
        self.req('/api/workspace/profile',{'version':start,'fields':{'education':old,'experience':'Old experience text'}})
        p=self.get();self.assertEqual(p['legacy']['education'],old);self.assertEqual(p['sections']['education']['items'],[])
        value={'items':[entry('education',qualification='BSc',institution='Synthetic College',start='2020',end='2024')]}
        self.assertEqual(self.save('education',value)['status'],200)
        self.assertEqual(self.get()['sections']['education'],value);self.assertEqual(self.get()['legacy']['education'],old)
        legacy=self.req('/api/workspace/profile')['body'];self.assertTrue(legacy['fields']['education'].startswith(old));self.assertIn('Synthetic College',legacy['fields']['education'])
        self.assertEqual(self.save('skills',{'items':['Python','APIs']})['status'],200)
        self.assertEqual(self.req('/api/workspace/profile')['body']['fields']['skills'],'Python, APIs')
        self.assertEqual(self.save('experience',{'no_experience':True,'items':[]})['status'],409)
    def test_each_section_persists_and_simple_fields_stay_compatible(self):
        self.signup()
        examples={'personal':{'name':'Updated Candidate','phone':'+91 0000000000','city':'Delhi','headline':'Python developer'},'summary':{'summary':'Synthetic summary'},'experience':{'items':[entry('experience',title='Developer',company='Synthetic Org',employment_type='Internship',start='2024-01',end='2024-06')],'no_experience':False},'projects':{'items':[entry('projects',name='Example project',contribution='Designed API',demo_url='https://example.com/demo')]},'certifications':{'items':[entry('certifications',name='Certificate',issuer='Example issuer',year='2024',credential_url='https://example.com/credential')]},'links':{'portfolio_url':'https://example.com','linkedin_url':'https://www.linkedin.com/in/synthetic','github_url':'https://github.com/synthetic'},'preferences':{'roles':'Developer','locations':'Delhi','work_mode':'remote','employment_type':'Full-time','availability':'After graduation'},'resume':{'resume_url':'https://example.com/resume'}}
        for section,value in examples.items():
            with self.subTest(section=section):
                r=self.save(section,value);self.assertEqual(r['status'],200,r);self.assertEqual(self.get()['sections'][section],value)
        self.assertEqual(self.req('/api/me')['body']['name'],'Updated Candidate')
        old=self.req('/api/workspace/profile')['body']
        self.assertEqual(old['fields']['summary'],'Synthetic summary');self.assertEqual(old['fields']['resume_url'],'https://example.com/resume');self.assertIn('Designed API',old['fields']['projects'])
        r=self.req('/api/workspace/profile',{'version':old['version'],'fields':{'resume_url':'https://example.com/new'}});self.assertEqual(r['status'],200,r)
        self.assertEqual(self.get()['sections']['resume']['resume_url'],'https://example.com/new');self.assertEqual(self.get()['sections']['projects'],examples['projects'])
        self.assertEqual(self.req('/api/workspace/candidate/recommendations')['body'],[])
    def test_authentication_csrf_roles_and_other_candidate_isolation(self):
        self.assertEqual(self.req(PATH)['status'],401)
        self.signup();first=self.cookie;self.save('summary',{'summary':'Only first candidate'})
        self.signup('other-profile@example.com');self.assertEqual(self.get()['sections']['summary']['summary'],'')
        self.assertEqual(self.req(PATH,cookie=first)['body']['sections']['summary']['summary'],'Only first candidate')
        r=self.req(PATH,{'version':0,'section':'summary','value':{'summary':'evil'}},origin='https://evil.example');self.assertEqual(r['status'],403)
        self.recruiter();self.login_recruiter();self.assertEqual(self.req(PATH)['status'],403)
        self.assertEqual(self.req('/api/workspace/profile')['body']['role'],'recruiter')
    def test_role_email_injection_and_bad_links_rejected(self):
        self.signup();before=self.get()['version']
        for section,value in [('personal',{'name':'Test','phone':'','city':'','headline':'','email':'other@example.com'}),('skills',{'items':['Python'],'admin':1}),('unknown',{}),('links',{'portfolio_url':'javascript:alert(1)','linkedin_url':'','github_url':''}),('links',{'portfolio_url':'https://user:pass@example.com','linkedin_url':'','github_url':''}),('resume',{'resume_url':'http://example.com'})]:
            with self.subTest(section=section):self.assertEqual(self.save(section,value)['status'],400)
        # Every save was rejected: the profile version must not have changed.
        self.assertEqual(self.get()['version'],before)
    def test_dates_limits_and_empty_records_rejected(self):
        bad=[('education',{'items':[entry('education',qualification='BSc',institution='X',start='2024',end='2020')]}),('experience',{'items':[entry('experience',title='Dev',company='X',start='2024-13')],'no_experience':False}),('education',{'items':[entry('education',qualification='BSc',institution='X',current=True,end='2025')]}),('projects',{'items':[entry('projects')]}),('skills',{'items':['Python','python']}),('skills',{'items':['x']*41}),('experience',{'items':[],'no_experience':'false'}),('summary',{'summary':'x'*2001})]
        for section,value in bad:
            with self.subTest(section=section),self.assertRaises(APIError):validate(section,value)
    def test_stale_version_never_overwrites_saved_data(self):
        self.signup();base=self.get()['version']
        self.assertEqual(self.save('summary',{'summary':'Saved'},base)['status'],200)
        self.assertEqual(self.save('summary',{'summary':'Stale'},base)['status'],409)
        self.assertEqual(self.get()['sections']['summary']['summary'],'Saved')
    def test_removal_and_fresher_choice_are_persisted_not_ranked(self):
        self.signup();value={'items':[entry('projects',name='Project')]};self.save('projects',value)
        self.assertEqual(self.save('projects',{'items':[]})['status'],200);self.assertEqual(self.get()['sections']['projects']['items'],[])
        self.assertEqual(self.save('experience',{'items':[],'no_experience':True})['status'],200)
        self.assertIn('No work experience yet',self.req('/api/workspace/profile')['body']['fields']['experience'])
    def test_old_editor_cannot_erase_structured_records(self):
        self.signup();self.save('education',{'items':[entry('education',qualification='BSc',institution='X')]})
        p=self.req('/api/workspace/profile')['body']
        self.assertEqual(self.req('/api/workspace/profile',{'version':p['version'],'fields':{'education':'Overwrite'}})['status'],409)
        self.assertEqual(len(self.get()['sections']['education']['items']),1)

@unittest.skipUnless(os.getenv('TEST_POSTGRES_URL'),'Disposable PostgreSQL not configured')
class ProfilePostgresTests(unittest.TestCase):
    setUp=PostgresJourney.setUp
    new_app=PostgresJourney.new_app
    def test_restart_and_cross_instance_version_conflict(self):
        # Use the common WSGI fixture helpers against local disposable PostgreSQL.
        self.cookie=''
        signup=fixtures.WorkspaceTests.signup(self);self.assertEqual(signup['status'],200)
        first=fixtures.WorkspaceTests.req(self,PATH)['body']
        r=fixtures.WorkspaceTests.req(self,PATH,{'version':first['version'],'section':'projects','value':{'items':[entry('projects',name='Persisted project')]}});self.assertEqual(r['status'],200,r)
        self.app=self.new_app();self.assertEqual(fixtures.WorkspaceTests.req(self,PATH)['body']['sections']['projects']['items'][0]['name'],'Persisted project')
        other=self.new_app();env={'PATH_INFO':PATH,'REQUEST_METHOD':'POST','HTTP_COOKIE':self.cookie}
        def save(app,value):
            try:return handle(app,env,{'version':1,'section':'summary','value':{'summary':value}})[0]['version']
            except APIError as e:return e.status
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures=[pool.submit(save,self.app,'First'),pool.submit(save,other,'Second')]
            self.assertEqual(sorted(f.result() for f in futures),[2,409])
    req=fixtures.WorkspaceTests.req
if __name__=='__main__':unittest.main()
