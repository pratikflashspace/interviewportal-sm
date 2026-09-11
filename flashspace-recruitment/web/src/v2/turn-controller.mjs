// Provider utterance boundaries are NOT full candidate-answer boundaries.
export class TurnController {
 constructor(clock=()=>performance.now()){
  this.clock=clock;this.epoch=0;this.state='paused';this.segments=new Map();
  this.pending=new Set();this.activeSpeech=new Set();this.ended=new Set();this.finalized=new Set();
  this.speaking=false;this.lastSpeech=null;this.finalAt=null;
 }
 valid(index){return Number.isInteger(index)&&index>=0;}
 inactive(){return this.state==='paused'||this.state==='completed';}
 begin(){
  this.epoch++;this.state='ai-speaking';this.segments.clear();this.pending.clear();
  this.activeSpeech.clear();this.ended.clear();this.finalized.clear();this.speaking=false;
  this.lastSpeech=null;this.finalAt=null;return this.epoch;
 }
 playbackEnded(token){
  if(token!==this.epoch||this.speaking||this.pending.size||this.inactive())return false;
  this.state='listening';return true;
 }
 speechStart(index){
  if(this.inactive()||!this.valid(index)||this.finalized.has(index)||this.ended.has(index)||this.segments.has(index))return false;
  this.epoch++;this.activeSpeech.add(index);this.pending.add(index);this.speaking=true;
  this.lastSpeech=this.clock();this.state='candidate-speaking';return true;
 }
 partial(index){
  if(this.inactive()||!this.valid(index)||this.finalized.has(index)||this.segments.has(index))return false;
  this.epoch++;this.pending.add(index);
  if(!this.ended.has(index))this.activeSpeech.add(index);
  this.speaking=this.activeSpeech.size>0;this.lastSpeech=this.clock();
  this.state=this.speaking?'candidate-speaking':'end-pending';return true;
 }
 speechEnd(index){
  if(this.inactive())return;
  // Current UI emits a global end only after the bridge's ordering guard has
  // observed all active utterances ending. Indexed callers remain supported.
  if(index===undefined){for(const i of this.activeSpeech)this.ended.add(i);this.activeSpeech.clear();}
  else {if(!this.valid(index))return;this.activeSpeech.delete(index);this.ended.add(index);}
  this.speaking=this.activeSpeech.size>0;this.lastSpeech=this.clock();
  this.state=this.speaking?'candidate-speaking':'end-pending';
 }
 final(index,text){
  if(this.inactive()||!this.valid(index)||typeof text!=='string'||this.finalized.has(index)||this.segments.has(index))return;
  this.finalized.add(index);this.pending.delete(index);
  if(text.trim())this.segments.set(index,text.trim());this.finalAt=this.clock();
 }
 transcript(){return [...this.segments.entries()].sort((a,b)=>a[0]-b[0]).map(x=>x[1]).join(' ');}
 ready(){return this.state==='end-pending'&&!this.speaking&&this.activeSpeech.size===0&&this.pending.size===0&&this.lastSpeech!==null&&this.finalAt!==null&&this.clock()-Math.max(this.lastSpeech,this.finalAt)>=6000&&this.transcript().length>0;}
 prepare(){if(!this.ready())return null;this.state='processing';return this.epoch;}
 canPlay(token){return token===this.epoch&&!this.speaking&&this.activeSpeech.size===0&&this.pending.size===0&&!this.inactive();}
 pause(){this.epoch++;this.speaking=false;this.activeSpeech.clear();this.state='paused';}
 complete(){this.pause();this.state='completed';}
}
