import test from 'node:test';
import assert from 'node:assert/strict';
import {revealedAt,visibleWords} from './question-reveal.mjs';
test('no question text before speech, null, NaN or missing metadata',()=>{
 for(const count of [undefined,null,NaN,0,-1])assert.equal(visibleWords('unspoken private question',count),'');
 for(const duration of [0,NaN,Infinity])assert.equal(revealedAt(2,duration,10),0);
 assert.equal(revealedAt(0,10,10),0);
});
test('playback controls reveal, lagging not predicting audio; no wall clock',()=>{
 assert.equal(revealedAt(5,10,10),4);assert.equal(revealedAt(5,10,10),4);
 assert.equal(visibleWords('one two three four five',2),'one two');
 assert.equal(visibleWords('one two three',100),'one two three');
 assert.equal(visibleWords('one two three',1.9),'one');
});
