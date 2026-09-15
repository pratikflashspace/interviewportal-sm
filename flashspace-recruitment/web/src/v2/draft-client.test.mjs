import test from 'node:test';
import assert from 'node:assert/strict';
import {DraftClient} from './draft-client.mjs';
test('writes use advancing revision and avoid duplicate posts',async()=>{
 let revision=0;const writes=[];const client=new DraftClient(async(path,body)=>{if(!body)return {question_id:'q',revision,transcript:''};assert.equal(body.revision,revision);writes.push(body.transcript);return {revision:++revision,transcript:body.transcript};});
 await client.load('a','q');await Promise.all([client.save('a','q','first'),client.save('a','q','second')]);await client.save('a','q','second');assert.deepEqual(writes,['first','second']);
});
test('switching question invalidates queued saves',async()=>{
 let release;let posted=0;const client=new DraftClient(async(path,body)=>{if(!body)return {question_id:'q',revision:0,transcript:''};posted++;await new Promise(r=>release=r);return {revision:1,transcript:body.transcript};});
 await client.load('a','q');const first=client.save('a','q','first');await Promise.resolve();const second=client.save('a','q','second');client.invalidate();release();await first;assert.equal(await second,null);assert.equal(posted,1);
});
test('conflicts surface without advancing the local revision',async()=>{
 const client=new DraftClient(async(path,body)=>{if(!body)return {question_id:'q',revision:3,transcript:'original'};throw Error('conflict');});await client.load('a','q');await assert.rejects(client.save('a','q','new'),/conflict/);assert.equal(client.current.revision,3);
});
