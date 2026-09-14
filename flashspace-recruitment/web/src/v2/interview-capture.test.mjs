import test from 'node:test';
import assert from 'node:assert/strict';
import {InterviewVoice} from './interview-capture.mjs';
class Track{constructor(kind){this.kind=kind;this.readyState='live';this.enabled=true;}stop(){this.readyState='ended';}}
class Stream{constructor(tracks){this.tracks=tracks;}getTracks(){return this.tracks;}getAudioTracks(){return this.tracks.filter(t=>t.kind==='audio');}getVideoTracks(){return this.tracks.filter(t=>t.kind==='video');}}
class Context{constructor(){this.sampleRate=16000;this.state='running';this.destination={speaker:true};this.connections=[];}async resume(){}async close(){this.state='closed';}createMediaStreamDestination(){return {stream:new Stream([new Track('audio')])};}source(){const connections=this.connections;return {connect:v=>connections.push(v),disconnect(){}};}createMediaStreamSource(){return this.source();}createMediaElementSource(){return this.source();}}
function setup(){const calls=[];const tracks=[new Track('audio')];const c=new InterviewVoice({api:async(p,b)=>{calls.push([p,b]);return {};},mediaDevices:{getUserMedia:async()=>new Stream(tracks)},Context,Stream});return {c,calls,tracks};}
test('one voice channel spans questions with no recorder or server calls',async()=>{const {c,calls,tracks}=setup();await c.begin();c.routeQuestion({});c.routeQuestion({});
 assert.equal(calls.length,0);assert.equal(c.state,'live');
 assert.ok(c.context.connections.includes(c.mix));assert.ok(c.context.connections.includes(c.context.destination));
 await c.stop();assert.ok(tracks.every(t=>t.readyState==='ended'));assert.equal(c.state,'stopped');});
test('microphone-only getUserMedia request',async()=>{let requested;const tracks=[new Track('audio')];const c=new InterviewVoice({mediaDevices:{getUserMedia:async r=>{requested=r;return new Stream(tracks);}},Context,Stream});await c.begin();assert.equal(requested.video,undefined);assert.ok(requested.audio);await c.stop();});
test('late permission grant after stop releases tracks',async()=>{const {c,tracks}=setup();let release;c.mediaDevices.getUserMedia=()=>new Promise(r=>release=r);const start=c.begin();await c.stop();release(new Stream(tracks));await assert.rejects(start,/cancelled/);assert.ok(tracks.every(t=>t.readyState==='ended'));});
test('microphone failure yields failed state',async()=>{const {c,tracks}=setup();await c.begin();tracks[0].onended();await c.stop();assert.equal(c.state,'failed');});
test('question audio reaches listening graph and playback destination',async()=>{const {c}=setup();await c.begin();c.routeQuestion({});assert.ok(c.context.connections.includes(c.mix));assert.ok(c.context.connections.includes(c.context.destination));await c.stop();});
