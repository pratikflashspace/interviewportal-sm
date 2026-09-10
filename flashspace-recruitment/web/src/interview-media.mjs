// One application-bound capture, continuous camera + mixed mic/interviewer audio.
export class InterviewMedia {
 constructor({application,call,fetcher=fetch,onFailure=()=>{},onState=()=>{}}){this.application=application;this.call=call;this.fetcher=fetcher;this.onFailure=onFailure;this.onState=onState;this.chain=Promise.resolve();this.parts=[];this.index=0;this.bytes=0;this.failed=false;this.closed=false;this.generation=0;}
 async start(){
  const token=++this.generation;const stream=await navigator.mediaDevices.getUserMedia({video:{width:{ideal:640},height:{ideal:480},frameRate:{ideal:15,max:20}},audio:{echoCancellation:true,noiseSuppression:true}});
  if(this.closed||token!==this.generation){stream.getTracks().forEach(t=>t.stop());throw Error('Interview capture cancelled.');}
  this.stream=stream;
  try{
   this.context=new AudioContext();await this.context.resume();
   this.mix=this.context.createMediaStreamDestination();
   this.mic=this.context.createMediaStreamSource(new MediaStream(stream.getAudioTracks()));this.mic.connect(this.mix);
   this.analyser=this.context.createAnalyser();this.analyser.fftSize=2048;this.mic.connect(this.analyser);this.samples=new Float32Array(2048);
   const mime=['video/webm;codecs=vp8,opus','video/webm','video/mp4'].find(t=>MediaRecorder.isTypeSupported(t));if(!mime)throw Error('This browser cannot record interview video.');
   this.mime=mime;this.slot=await this.call('/recordings',{application_id:this.application,mime:mime.split(';')[0],consent:'temporary-av-v1'});
   if(this.closed||token!==this.generation)throw Error('Interview capture cancelled.');
   this.recorder=new MediaRecorder(new MediaStream([...stream.getVideoTracks(),...this.mix.stream.getAudioTracks()]),{mimeType:mime,videoBitsPerSecond:350000,audioBitsPerSecond:48000});
   this.done=new Promise(resolve=>this.resolveDone=resolve);
   this.recorder.ondataavailable=e=>{
    if(!e.data.size)return;
    if(this.bytes+e.data.size>50*1024*1024){this.fail('Recording size limit reached. Interview paused; save the partial local recording.');return;}
    this.bytes+=e.data.size;this.parts.push(e.data);
    this.chain=this.chain.then(async()=>{if(this.failed)return;for(let i=0;i<e.data.size;i+=1048576){await this.chunk(this.index,e.data.slice(i,i+1048576));this.index++;}}).catch(e=>this.fail(e.message));
   };
   this.recorder.onstop=()=>this.resolveDone();this.recorder.onerror=()=>this.fail('Recording failed. Interview paused.');
   stream.getTracks().forEach(t=>t.onended=()=>{if(!this.closed)this.fail('Camera or microphone disconnected. Interview paused.');});
   this.recorder.start(2000);this.onState('recording');
   this.limit=setTimeout(()=>this.fail('10-minute recording limit reached. Interview paused; finish this segment before resuming.'),600000);
   return stream;
  }catch(e){this.dispose();throw e;}
 }
 level(){if(!this.analyser)return 0;this.analyser.getFloatTimeDomainData(this.samples);return Math.sqrt(this.samples.reduce((s,x)=>s+x*x,0)/this.samples.length);}
 async chunk(index,blob){let last;for(let attempt=0;attempt<3;attempt++){try{const r=await this.fetcher('/api/recordings/'+this.slot.id+'/chunk/'+index,{method:'POST',credentials:'same-origin',headers:{'X-Requested-With':'Flashspace','Content-Type':'application/octet-stream'},body:blob});if(!r.ok)throw Error((await r.json()).error||'Upload rejected.');return;}catch(e){last=e;if(attempt<2)await new Promise(r=>setTimeout(r,1000*(attempt+1)));}}throw last;}
 async play(blob){
  this.stopPlayback();const buffer=await this.context.decodeAudioData(await blob.arrayBuffer());
  if(this.closed)throw Error('Capture is no longer active.');
  return new Promise(resolve=>{const source=this.context.createBufferSource();source.buffer=buffer;source.connect(this.context.destination);source.connect(this.mix);source.onended=()=>{if(this.playing?.source===source)this.playing=null;resolve();};this.playing={source,resolve};source.start();});
 }
 stopPlayback(){if(this.playing){const p=this.playing;this.playing=null;p.source.onended=null;try{p.source.stop();}catch{}p.resolve();}}
 fail(message){if(this.failed)return;this.failed=true;this.onFailure(message);}
 async finish(){
  if(this.finishing)return this.finishing;
  this.finishing=(async()=>{
   this.closed=true;this.generation++;clearTimeout(this.limit);this.stopPlayback();
   if(this.recorder?.state==='recording')this.recorder.stop();
   // Allow the encoder to flush while its source tracks are still live. Release
   // tracks after stop, with a bounded fallback if a broken browser never emits it.
   if(this.done){let timeout;await Promise.race([this.done,new Promise(resolve=>timeout=setTimeout(()=>{this.failed=true;resolve();},5000))]);clearTimeout(timeout);}
   this.stream?.getTracks().forEach(t=>t.stop());this.mix?.stream.getTracks().forEach(t=>t.stop());await this.chain;
   const blob=new Blob(this.parts,{type:this.mime||'video/webm'});
   let error=null;try{if(this.failed||!this.index)throw Error('Server recording is incomplete. Keep the local download.');await this.call('/recordings/'+this.slot.id+'/finish',{chunks:this.index});}catch(e){error=e.message;}
   this.dispose();return {blob,error,recording:this.slot?.id};
  })();return this.finishing;
 }
 dispose(){this.closed=true;this.generation++;clearTimeout(this.limit);this.stopPlayback();if(this.recorder?.state==='recording')this.recorder.stop();this.stream?.getTracks().forEach(t=>t.stop());this.mix?.stream.getTracks().forEach(t=>t.stop());if(this.context&&this.context.state!=='closed')this.context.close();}
}
