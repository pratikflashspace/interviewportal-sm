// The interviewer's question arrives word by word, in step with the audio,
// rather than sitting fully written on screen before the voice starts.
//
// Unspoken words keep their space and are only made invisible, so the card
// never reflows mid-sentence. Assistive technology always gets the whole
// question at once from the visually hidden copy: a reveal that is paced for
// listening would be an obstacle, not an effect, for a screen reader.
import React from 'react';

export function wordsOf(text){return String(text||'').trim().split(/\s+/).filter(Boolean);}

// How many words should be showing at this point in the audio. Shared by the
// interview room and the preview harness so both pace identically. Without
// usable metadata, fall back to elapsed time at a normal speaking rate.
export function revealedAt(at,duration,total){
 if(!total)return 0;
 const ratio=Number.isFinite(duration)&&duration>0?at/duration:Math.min(1,at/(total/2.6));
 return Math.max(0,Math.min(total,Math.round(ratio*total)));
}

export default function SpokenQuestion({text='',revealed=null}){
 const words=wordsOf(text);
 // `revealed === null` means "not being spoken": show the question in full.
 const shown=revealed===null?words.length:Math.max(0,Math.min(words.length,revealed));
 return <h3 className={'interview-question'+(revealed===null?'':' is-revealing')}>
  <span className="interview-sr">{text}</span>
  <span aria-hidden="true">{words.map((word,i)=>
   <span key={i} className={'interview-word'+(i<shown?' is-spoken':'')}>{word}{i<words.length-1?' ':''}</span>)}
  </span>
 </h3>;
}
