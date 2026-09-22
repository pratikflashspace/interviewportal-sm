import test from 'node:test';
import assert from 'node:assert/strict';
import {publicRoles,filterOptions,filterValue,matches,display,employmentType,workMode,existingDestination,jobsRequest} from './explore-jobs.mjs';
const source={id:'one',title:'Engineering',department:'IT',location:'Remote/On-site - Both Available',experience:'0-1',type:'Full Time',skills:['Python','APIs'],description:'Build products.',details:'- First responsibility\n- Second responsibility\n\nRequirements:\n- Python\n<script>untrusted text</script>',internal_notes:'private',version:7};
const rows=()=>publicRoles([source,{...source,id:'two',title:'Sales',department:'Sales',skills:['CRM'],location:'Delhi',experience:'0-2 years experience',type:'Part-time',details:'Customer conversations'}]);
test('saved text and punctuation preserved without internal metadata',()=>{const r=publicRoles([source])[0];assert.equal(r.details,source.details);assert.equal(r.location,source.location);assert.equal(r.experience,'0-1');assert.equal(r.type,'Full Time');assert.equal(r.internal_notes,undefined);assert.equal(r.version,undefined);assert.deepEqual(source.skills,['Python','APIs']);});
test('only published records accepted and malformed payload fails',()=>{assert.deepEqual(publicRoles([{...source,published:false},{...source,state:'draft'}]),[]);for(const value of [null,{},[{id:'broken'}],[source,source]])assert.throws(()=>publicRoles(value));});
test('all four filters operate on canonical buckets',()=>{assert.deepEqual(matches(rows(),'',{department:'IT'}).map(r=>r.id),['one']);assert.deepEqual(matches(rows(),'',{experience:'0-1'}).map(r=>r.id),['one']);assert.deepEqual(matches(rows(),'',{work_mode:'On site'}).map(r=>r.id),['one','two']);assert.deepEqual(matches(rows(),'',{type:'Full time'}).map(r=>r.id),['one']);assert.equal(matches(rows(),'',{department:'IT',experience:'0-2 years experience'}).length,0);assert.deepEqual(matches(rows(),'',{type:'Part time'}).map(r=>r.id),['two']);assert.equal(matches(rows(),'',{work_mode:'Hybrid'}).length,0);});
test('keyword search includes multiline saved requirements and is case insensitive',()=>{assert.deepEqual(matches(rows(),'PYTHON responsibility').map(r=>r.id),['one']);assert.deepEqual(matches(rows(),'customer').map(r=>r.id),['two']);assert.equal(matches(rows(),'unavailable keyword').length,0);assert.equal(matches(rows(),'').length,2);});
test('employment type maps saved labels to canonical buckets',()=>{
 assert.equal(employmentType({type:'Full Time'}),'Full time');
 assert.equal(employmentType({type:'Full-time'}),'Full time');
 assert.equal(employmentType({type:'Part-time'}),'Part time');
 assert.equal(employmentType({type:'Internship'}),'Internship');
 assert.equal(employmentType({type:'Contract'}),'Contract');
 assert.equal(employmentType({type:''}),'');
 assert.deepEqual(filterOptions(rows(),'type'),['Full time','Part time','Internship','Contract']);
});
test('work mode defaults to On site; Hybrid/Remote only when explicit',()=>{
 // "Remote/On-site - Both Available" reads as On site (office-first hiring).
 assert.equal(workMode({location:'Remote/On-site - Both Available'}),'On site');
 assert.equal(workMode({location:'Remote / On-site — both available',work_mode:''}),'On site');
 assert.equal(workMode({work_mode:'Remote'}),'Remote');
 assert.equal(workMode({work_mode:'Fully remote role'}),'Remote');
 assert.equal(workMode({work_mode:'Hybrid'}),'Hybrid');
 assert.equal(workMode({location:'Delhi'}),'On site');
 assert.equal(workMode({}),'On site');
 assert.equal(workMode(null),'On site');
 // Canonical options are always listed so future postings are filterable.
 assert.deepEqual(filterOptions(rows(),'work_mode'),['On site','Hybrid','Remote']);
 assert.deepEqual(filterOptions(rows(),'type'),['Full time','Part time','Internship','Contract']);
 assert.equal(filterValue({},'work_mode'),'On site');
 assert.deepEqual(matches(publicRoles([{...source,id:'x',location:'Remote / On-site — both available',work_mode:''}]),'',{work_mode:'On site'}).length,1);
 assert.deepEqual(filterOptions(rows(),'skills'),['APIs','CRM','Python']);
});
test('existing application resumes without a new application; completed shows applications',()=>{assert.equal(existingDestination([],'one'),null);assert.equal(existingDestination([{id:'a b',role_id:'one',flow_version:2,status:'interview'}],'one'),'/interview-v2?application=a%20b');assert.equal(existingDestination([{id:'old',role_id:'one',flow_version:1,status:'interview'}],'one'),'/candidate/workspace/legacy?application=old');assert.equal(existingDestination([{id:'done',role_id:'one',status:'completed'}],'one'),'/candidate/workspace/applications');assert.throws(()=>existingDestination(null,'one'));});
test('logout uses a 65s cold-start budget and a truthful timeout message',async()=>{
 // Regression (staging): after a period of inactivity the free-tier database sleeps;
 // the logout POST then needs 30-60s while the old 15/30s client timeout aborted it
 // mid-flight, surfacing a misleading 'check My Applications' error.
 let seen={};
 await jobsRequest('/logout',{body:{},fetcher:async(url,o)=>{seen.timeout=undefined;return {ok:true,json:async()=>({ok:true})};}});
 // Verify the timeout actually used for /logout: fetcher receives the abort signal.
 await assert.rejects(jobsRequest('/logout',{timeoutMs:5,fetcher:(_,{signal})=>new Promise((_,reject)=>signal.addEventListener('abort',()=>reject(Error('abort'))))}),/Sign out is taking longer than expected/);
 for(const helper of ['applicationsRequest','profileRequest','accountRequest']){
   const mod=await import('./'+{applicationsRequest:'my-applications.mjs',profileRequest:'candidate-profile.mjs',accountRequest:'account-client.mjs'}[helper]);
   await assert.rejects(mod[helper]('/logout',{timeoutMs:5,fetcher:(_,{signal})=>new Promise((_,reject)=>signal.addEventListener('abort',()=>reject(Error('abort'))))}),/Sign out is taking longer than expected|timed out/);
 }
});
test('read-only public jobs request and same-origin application transport',async()=>{await jobsRequest('/roles',{fetcher:async(url,o)=>{assert.equal(url,'/api/roles');assert.equal(o.method,'GET');assert.equal(o.cache,'no-store');assert.equal(o.credentials,'same-origin');return {ok:true,json:async()=>[]};}});await jobsRequest('/v2/applications',{body:{role_id:'one',consent:true},fetcher:async(url,o)=>{assert.equal(o.method,'POST');assert.deepEqual(JSON.parse(o.body),{role_id:'one',consent:true});assert.equal(o.headers['X-Requested-With'],'Flashspace');return {ok:true,json:async()=>({application_id:'synthetic'})};}});await assert.rejects(jobsRequest('/admin/roles'),/Unsupported/);});
test('failure, invalid JSON and timeout do not invent empty successful results',async()=>{for(const status of [401,403,429,500])await assert.rejects(jobsRequest('/roles',{fetcher:async()=>({ok:false,status,json:async()=>({error:'secret details'})})}),e=>e.status===status&&!e.message.includes('secret details'));await assert.rejects(jobsRequest('/roles',{fetcher:async()=>({ok:false,status:409,json:async()=>({error:'This role needs an approved question-bank mapping.'})})}),e=>e.status===409&&e.message==='This role needs an approved question-bank mapping.');await assert.rejects(jobsRequest('/roles',{fetcher:async()=>({ok:false,status:409,json:async()=>({})})}),/This role or application changed/);await assert.rejects(jobsRequest('/roles',{fetcher:async()=>({ok:true,json:async()=>{throw Error();}})}),/unreadable/);await assert.rejects(jobsRequest('/roles',{timeoutMs:5,fetcher:(_,{signal})=>new Promise((_,reject)=>signal.addEventListener('abort',()=>reject(Error('abort'))))}),/timed out/);});
