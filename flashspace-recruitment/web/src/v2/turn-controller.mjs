// Pure turn arbitration; provider utterance boundaries are NOT full answers.
export class TurnController {
 constructor(clock=()=>performance.now()){this.clock=clock;this.epoch=0;this.state='paused';this.segments=new Map();this.pending=new Set();this.speaking=false;this.lastSpeech=null;this.finalAt=null;}
 begin(){this.epoch++;this.state='ai-speaking';this.segments.clear();this.pending.clear();this.speaking=false;this.lastSpeech=null;this.finalAt=null;return this.epoch;}
 playbackEnded(token){if(token!==this.epoch||this.speaking||this.state==='paused')return false;this.state='listening';return true;}
 speechStart(index){if(this.state==='paused'||this.state==='completed')return false;this.epoch++;this.speaking=true;this.lastSpeech=this.clock();this.pending.add(index);this.state='candidate-speaking';return true;}
 partial(index){if(this.state==='paused'||this.state==='completed'||this.segments.has(index))return;this.pending.add(index);this.lastSpeech=this.clock();this.epoch++;}
 speechEnd(){if(this.state==='paused'||this.state==='completed')return;this.speaking=false;this.lastSpeech=this.clock();this.state='end-pending';}
 final(index,text){if(this.state==='paused'||this.state==='completed'||this.segments.has(index))return;this.pending.delete(index);if(text.trim())this.segments.set(index,text.trim());this.finalAt=this.clock();}
 transcript(){return [...this.segments.entries()].sort((a,b)=>a[0]-b[0]).map(x=>x[1]).join(' ');}
 ready(){return this.state==='end-pending'&&!this.speaking&&this.pending.size===0&&this.lastSpeech!==null&&this.finalAt!==null&&this.clock()-Math.max(this.lastSpeech,this.finalAt)>=6000&&this.transcript().length>0;}
 prepare(){if(!this.ready())return null;this.state='processing';return this.epoch;}
 canPlay(token){return token===this.epoch&&!this.speaking&&this.state!=='paused'&&this.state!=='completed';}
 pause(){this.epoch++;this.speaking=false;this.state='paused';}
 complete(){this.pause();this.state='completed';}
}
