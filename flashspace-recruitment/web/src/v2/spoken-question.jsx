// Never render undisclosed question words, including screen-reader-only text.
import React from 'react';
import {visibleWords} from './question-reveal.mjs';
export {wordsOf,revealedAt} from './question-reveal.mjs';
export default function SpokenQuestion({text='',revealed=0}){
 const visible=visibleWords(text,revealed);
 return <h3 className="interview-question" aria-live="off">{visible||'Listen to your interviewer. The question will appear here as it is spoken.'}</h3>;
}
