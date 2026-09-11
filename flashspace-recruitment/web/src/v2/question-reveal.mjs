// Conservative playback-based approximation, not provider word timestamps.
export function wordsOf(text){return String(text||'').trim().split(/\s+/).filter(Boolean);}
export function revealedAt(at,duration,total){
 if(!Number.isFinite(at)||at<=0||!Number.isFinite(duration)||duration<=0||total<=0)return 0;
 // Slightly lag playback; unavailable metadata never exposes a whole question.
 return Math.max(0,Math.min(total,Math.floor(Math.max(0,at-.2)/duration*total)));
}
export function visibleWords(text,revealed=0){
 const words=wordsOf(text);
 const count=Number.isFinite(revealed)?Math.floor(revealed):0;
 return words.slice(0,Math.max(0,Math.min(words.length,count))).join(' ');
}
