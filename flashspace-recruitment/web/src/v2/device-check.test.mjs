import test from 'node:test';
import assert from 'node:assert/strict';
import {DeviceCheck} from './device-check.mjs';
function fixture(){
 const tracks=[{kind:'video',stopped:false,stop(){this.stopped=true;}},{kind:'audio',stopped:false,stop(){this.stopped=true;}}];
 const stream={getTracks:()=>tracks,getVideoTracks:()=>tracks.filter(t=>t.kind==='video'),getAudioTracks:()=>tracks.filter(t=>t.kind==='audio')};
 const nodes=[];const node=()=>{const n={connect(){},disconnect(){this.disconnected=true;}};nodes.push(n);return n;};
 class Context{constructor(){this.sampleRate=16000;this.state='suspended';this.currentTime=0;this.destination={};}async resume(){this.state='running';}async close(){this.state='closed';}createMediaStreamSource(){return node();}createAnalyser(){return {...node(),getByteTimeDomainData(a){a.fill(150);}};}createOscillator(){return {...node(),frequency:{value:0},start(){},stop(){}};}createGain(){return {...node(),gain:{value:0}};}}
 let constructed=0;class Recorder{constructor(){constructed++;}static isTypeSupported(){return true;}}
 return {tracks,stream,Context,Recorder,get constructed(){return constructed;}};
}
test('device preview opens camera/mic without constructing recorder or calling any server',async()=>{
 const f=fixture();const check=new DeviceCheck({devices:{getUserMedia:async()=>f.stream},Context:f.Context,Recorder:f.Recorder});
 assert.equal(await check.open(),f.stream);assert(check.level()>0);check.tone();assert.equal(f.constructed,0);
 await check.close();assert(f.tracks.every(t=>t.stopped));assert.equal(check.stream,null);
});
test('cancel while permission prompt pending stops late granted tracks',async()=>{
 const f=fixture();let grant;const permission=new Promise(resolve=>grant=resolve);const check=new DeviceCheck({devices:{getUserMedia:()=>permission},Context:f.Context,Recorder:f.Recorder});
 const pending=check.open();await new Promise(r=>setImmediate(r));await check.close();grant(f.stream);await assert.rejects(pending,/cancelled/);assert(f.tracks.every(t=>t.stopped));assert.equal(f.constructed,0);
});
test('permission denial and incompatible audio fail without recording',async()=>{
 const f=fixture();const check=new DeviceCheck({devices:{getUserMedia:async()=>{throw Error('permission denied');}},Context:f.Context,Recorder:f.Recorder});await assert.rejects(check.open(),/permission denied/);assert.equal(f.constructed,0);
 class WrongContext extends f.Context{constructor(){super();this.sampleRate=48000;}}
 const wrong=new DeviceCheck({devices:{getUserMedia:async()=>f.stream},Context:WrongContext,Recorder:f.Recorder});await assert.rejects(wrong.open(),/audio format/);assert(f.tracks.every(t=>t.stopped));
});
