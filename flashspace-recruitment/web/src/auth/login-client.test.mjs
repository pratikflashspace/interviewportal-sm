import test from 'node:test';
import assert from 'node:assert/strict';
import {loginManually,loginDestination,SERVICE_ERROR} from './login-client.mjs';
const credentials={email:' candidate@example.com ',password:' synthetic password '};
const response=(status,user)=>({status,ok:status===200,json:async()=>user});
test('candidate request preserves password and uses correct secure request options',async()=>{
 let call;const user=await loginManually('candidate',credentials,{fetcher:async(...args)=>{call=args;return response(200,{role:'candidate',admin:false});}});
 assert.equal(user.role,'candidate');assert.equal(call[0],'/api/auth/candidate/login');assert.equal(call[1].credentials,'same-origin');assert.equal(call[1].method,'POST');assert.equal(call[1].headers['X-Requested-With'],'Flashspace');assert.equal(call[1].cache,'no-store');assert.deepEqual(JSON.parse(call[1].body),{email:'candidate@example.com',password:credentials.password});
});
test('recruiter has its own endpoint and dashboard',async()=>{
 let url;await loginManually('recruiter',credentials,{fetcher:async u=>{url=u;return response(200,{role:'recruiter',admin:true});}});
 assert.equal(url,'/api/auth/recruiter/login');assert.equal(loginDestination('recruiter'),'/recruiter/workspace/dashboard');assert.equal(loginDestination('candidate'),'/candidate/workspace/dashboard');
});
test('credentials and throttling errors are clear',async()=>{
 await assert.rejects(loginManually('candidate',credentials,{fetcher:async()=>response(401,{error:'raw internal message'})}),/Email or password is incorrect/);
 await assert.rejects(loginManually('candidate',credentials,{fetcher:async()=>response(429)}),/Too many sign-in attempts/);
});
test('missing route, server error and CSRF rejection do not blame the email',async()=>{
 for(const status of [403,404,410,500,503])await assert.rejects(loginManually('candidate',credentials,{fetcher:async()=>response(status,{error:'Not found.'})}),{message:SERVICE_ERROR});
});
test('mismatched role and malformed success never navigate',async()=>{
 for(const data of [null,{}, {role:'recruiter',admin:true},{role:'candidate',admin:true},{role:'candidate'}])await assert.rejects(loginManually('candidate',credentials,{fetcher:async()=>response(200,data)}),{message:SERVICE_ERROR});
 await assert.rejects(loginManually('candidate',credentials,{fetcher:async()=>({status:200,ok:true,json:async()=>{throw Error('bad JSON');}})}),{message:SERVICE_ERROR});
});
test('invalid role makes no network request',async()=>{
 let called=false;await assert.rejects(loginManually('admin',credentials,{fetcher:async()=>{called=true;}}));assert.equal(called,false);
});
test('network failures have no raw error or secrets',async()=>{
 await assert.rejects(loginManually('candidate',credentials,{fetcher:async()=>{throw TypeError('sensitive raw error');}}),/Unable to connect/);
});
test('timeout aborts request once with no automatic retry',async()=>{
 let count=0;await assert.rejects(loginManually('candidate',credentials,{timeoutMs:5,fetcher:async(_url,{signal})=>{count++;return new Promise((_resolve,reject)=>signal.addEventListener('abort',()=>reject(Error('aborted'))));}}),/Sign-in timed out/);assert.equal(count,1);
});
test('caller abort is propagated',async()=>{
 const controller=new AbortController();const work=loginManually('candidate',credentials,{signal:controller.signal,fetcher:async(_url,{signal})=>new Promise((_resolve,reject)=>signal.addEventListener('abort',()=>reject(Error('aborted'))))});controller.abort();await assert.rejects(work,/Sign-in cancelled/);
});
