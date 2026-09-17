import test from 'node:test';
import assert from 'node:assert/strict';
import {googleRequest} from './candidate-google-client.mjs';
const reply=(body,status=200)=>({ok:status===200,status,json:async()=>body});
test('config reports disabled without contacting Google',async()=>{
 let calls=0;const r=await googleRequest('config',{fetcher:async(url,options)=>{calls++;assert.equal(url,'/api/auth/candidate/google/config');assert.equal(options.method,'GET');assert.equal(options.body,undefined);return reply({enabled:false});}});assert.equal(r.enabled,false);assert.equal(calls,1);
});
test('credential is POST body only, same origin and no retry',async()=>{
 let calls=0;const r=await googleRequest('login',{credential:'synthetic-token',fetcher:async(url,o)=>{calls++;assert.equal(url,'/api/auth/candidate/google');assert.equal(o.credentials,'same-origin');assert.equal(o.cache,'no-store');assert.equal(o.headers['X-Requested-With'],'Flashspace');assert.deepEqual(JSON.parse(o.body),{credential:'synthetic-token'});return reply({role:'candidate',admin:false});}});assert.equal(calls,1);assert.equal(r.role,'candidate');
});
test('recruiter or malformed successful response cannot authenticate',async()=>{
 for(const body of [{role:'recruiter',admin:true},{role:'candidate',admin:true},{role:'candidate'},null])await assert.rejects(googleRequest('login',{credential:'synthetic',fetcher:async()=>reply(body)}),/candidate account/);
});
test('server error messages are not reflected and no implicit linking',async()=>{
 for(const status of [401,403,409,429,503,500]){
  let calls=0;await assert.rejects(googleRequest('login',{credential:'synthetic',fetcher:async()=>{calls++;return reply({error:'private-token-details'},status);}}),error=>!error.message.includes('private-token-details'));assert.equal(calls,1);
 }
});
test('challenge validates nonce and client format',async()=>{
 const valid={client_id:'synthetic.apps.googleusercontent.com',nonce:'a'.repeat(64),expires_in:300};assert.deepEqual(await googleRequest('challenge',{fetcher:async()=>reply(valid)}),valid);
 for(const changes of [{nonce:'short'},{client_id:'https://evil.example'},{expires_in:99999}])await assert.rejects(googleRequest('challenge',{fetcher:async()=>reply({...valid,...changes})}),/configuration/);
});
test('timeout aborts without retry',async()=>{
 let calls=0;await assert.rejects(googleRequest('login',{credential:'synthetic',timeoutMs:5,fetcher:(_url,{signal})=>new Promise((_resolve,reject)=>{calls++;signal.addEventListener('abort',()=>reject(Error('aborted')));})}),/timed out/);assert.equal(calls,1);
});
test('caller cancellation and malformed JSON fail safely',async()=>{
 const controller=new AbortController();controller.abort();await assert.rejects(googleRequest('config',{signal:controller.signal,fetcher:async(_url,{signal})=>{assert.equal(signal.aborted,true);throw Error('aborted');}}),/stopped/);
 await assert.rejects(googleRequest('config',{fetcher:async()=>({ok:true,json:async()=>{throw Error('bad json');}})}),/invalid response/);
});
