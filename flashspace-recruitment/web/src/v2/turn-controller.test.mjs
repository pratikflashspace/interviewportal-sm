import test from 'node:test';
import assert from 'node:assert/strict';
import {TurnController} from './turn-controller.mjs';
import './draft-client.test.mjs';
function setup(){let now=0;const c=new TurnController(()=>now);c.begin();c.playbackEnded(c.epoch);return {c,time:v=>now=v};}
test('short thinking pauses never finalize',()=>{const {c,time}=setup();c.speechStart(0);c.speechEnd();c.final(0,'My answer');for(const n of [1000,3000,5000]){time(n);assert.equal(c.ready(),false);}time(6000);assert.equal(c.ready(),true);});
test('initial silence never becomes an answer',()=>{const {c,time}=setup();time(60000);assert.equal(c.ready(),false);});
test('resumed speech invalidates delayed processing/playback',()=>{const {c,time}=setup();c.speechStart(0);c.speechEnd();c.final(0,'First thought');time(7000);const token=c.prepare();c.speechStart(1);assert.equal(c.canPlay(token),false);assert.equal(c.ready(),false);c.speechEnd();c.final(1,'Then another thought');time(14000);assert.equal(c.ready(),true);assert.equal(c.transcript(),'First thought Then another thought');});
test('late finals and duplicate segments are safe',()=>{const {c,time}=setup();c.speechStart(0);c.speechEnd();time(10000);assert.equal(c.ready(),false);c.final(0,'Answer');c.final(0,'Answer');time(15000);assert.equal(c.ready(),false);time(16000);assert.equal(c.ready(),true);assert.equal(c.transcript(),'Answer');});
test('pause suppresses late callbacks and speech',()=>{const {c}=setup();const token=c.epoch;c.pause();c.final(0,'late');assert.equal(c.playbackEnded(token),false);assert.equal(c.canPlay(token),false);assert.equal(c.speechStart(1),false);assert.equal(c.transcript(),'');});
test('late partial for an already finalized utterance cannot reopen it',()=>{const {c,time}=setup();c.speechStart(0);c.speechEnd();c.final(0,'Answer');time(4000);c.partial(0);c.final(0,'duplicate');time(6000);assert.equal(c.ready(),true);assert.equal(c.transcript(),'Answer');});
