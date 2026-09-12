// One application-owned recording; lifecycle independent from per-turn STT.
export class InterviewCapture {
 constructor({api,upload,mediaDevices=globalThis.navigator?.mediaDevices,Context=globalThis.AudioContext,Recorder=globalThis.MediaRecorder,Stream=globalThis.MediaStream,onChange=()=>{},onFailure=()=>{}}){
  Object.assign(this,{api,upload,mediaDevices,Context,Recorder,Stream,onChange,onFailure});
  this.state='idle';this.generation=0;this.parts=[];this.bytes=0;this.index=0;this.queue=Promise.resolve();this.failed=false;this.stopPromise=null;this.queuedBytes=0;this.sources=new Set();
 }
 notify(state){this.state=state;this.onChange({state,bytes:this.bytes,id:this.id,blob:this.blob,mime:this.mime});}
 assertCurrent(generation){if(generation!==this.generation)throw Error('Interview start cancelled.');}
 async prepareSpeechWorklet(){
  if(this.speechWorkletReady)return;
  if(!this.context?.audioWorklet)throw Error('This browser does not support live interview audio processing.');
  let timer;
  try{await Promise.race([this.context.audioWorklet.addModule('/v2-pcm-worklet.js'),new Promise((_,reject)=>{timer=setTimeout(()=>reject(Error('Audio processing setup timed out. No interview recording was started.')),10000);})]);this.speechWorkletReady=true;}
  finally{clearTimeout(timer);}
 }
 async begin(applicationId,consent){
  if(!consent)throw Error('Camera and audio recording consent is required.');
  if(!['idle','failed','saved','cancelled'].includes(this.state))throw Error('Recording is already active.');
  this.recorder=null;this.id=null;this.finished=null;this.stopPromise=null;this.failed=false;this.blob=null;this.speechWorkletReady=false;
  this.voiceMeter=null;this.questionMeter=null;
  const generation=++this.generation;this.notify('permission');let stream;
  try{
   stream=await this.mediaDevices.getUserMedia({video:{width:{ideal:640},height:{ideal:480},frameRate:{ideal:15,max:20}},audio:{echoCancellation:true,noiseSuppression:true,channelCount:1}});
   this.assertCurrent(generation);
   if(!stream.getVideoTracks().length||!stream.getAudioTracks().length)throw Error('Camera and microphone are both required.');
   this.stream=stream;this.context=new this.Context({sampleRate:16000});
   if(this.context.sampleRate!==16000)throw Error('This browser cannot provide 16 kHz interview audio.');
   await this.context.resume();this.assertCurrent(generation);
   // Complete worklet registration before connecting the recording graph. A
   // stalled addModule must not leave the camera recording an idle interview.
   // The actual browser context exposes audioWorklet; older media-only unit
   // test doubles do not. The room independently requires it before listening.
   if(this.context.audioWorklet){await this.prepareSpeechWorklet();this.assertCurrent(generation);}
   this.mix=this.context.createMediaStreamDestination();
   this.microphone=this.context.createMediaStreamSource(new this.Stream(stream.getAudioTracks()));this.microphone.connect(this.mix);
   this.voiceMeter=this.meter();this.questionMeter=this.meter();
   if(this.voiceMeter)this.microphone.connect(this.voiceMeter);
   const mime=['video/webm;codecs=vp8,opus','video/webm','video/mp4'].find(t=>this.Recorder.isTypeSupported(t));
   if(!mime)throw Error('No compatible recording format.');
   this.mime=mime;
   const slot=await this.api('/v2/applications/'+applicationId+'/recording',{consent:'integrated-interview-av-v1',mime:mime.split(';')[0]});
   this.id=slot.id;this.applicationId=applicationId;this.assertCurrent(generation);
   this.parts=[];this.bytes=0;this.index=0;this.queue=Promise.resolve();this.queuedBytes=0;
   this.limit=slot.max_bytes;this.remainingSeconds=slot.max_seconds;this.activeMs=0;this.lastTick=performance.now();
   const combined=new this.Stream([...stream.getVideoTracks(),...this.mix.stream.getAudioTracks()]);
   this.recorder=new this.Recorder(combined,{mimeType:mime,videoBitsPerSecond:350000,audioBitsPerSecond:48000});
   this.finished=new Promise(resolve=>{this.resolveFinished=resolve;});
   this.recorder.ondataavailable=e=>this.acceptChunk(e.data);
   this.recorder.onerror=()=>this.fail('Recording device error; interview paused.');
   this.recorder.onstop=()=>this.finalize();
   stream.getTracks().forEach(t=>t.onended=()=>{if(['recording','paused'].includes(this.state))this.fail('Camera or microphone disconnected; interview paused.');});
   this.assertCurrent(generation);this.recorder.start(2000);this.notify('recording');
   this.timer=setInterval(()=>{const now=performance.now();if(this.state==='recording')this.activeMs+=now-this.lastTick;this.lastTick=now;if(this.activeMs>=this.remainingSeconds*1000)this.fail('Recording time limit reached. Captured portion retained; do not treat it as a complete recording.');},1000);
   return stream;
  }catch(e){
   stream?.getTracks().forEach(t=>t.stop());await this.release();
   if(this.id)await this.api('/recordings/'+this.id+'/abort',{}).catch(()=>{});
   this.notify(generation===this.generation?'failed':'cancelled');throw e;
  }
 }
 acceptChunk(blob){
  if(!blob?.size)return;
  if(this.bytes+blob.size>this.limit){this.fail('Recording storage limit reached; captured portion is incomplete.');return;}
  this.bytes+=blob.size;this.parts.push(blob);this.queuedBytes+=blob.size;
  if(this.queuedBytes>8*1048576){this.fail('Upload is falling behind. Interview stopped to prevent unbounded recording queues.');return;}
  this.queue=this.queue.then(async()=>{
   if(this.failed)return;
   for(let offset=0;offset<blob.size;offset+=1048576){
    const chunk=blob.slice(offset,offset+1048576);let success=false;
    for(let attempt=0;attempt<3&&!success;attempt++){
     try{await this.upload(this.id,this.index,chunk);success=true;}catch(e){if(attempt===2)throw e;await new Promise(r=>setTimeout(r,500*(attempt+1)));}
    }
    this.index++;
   }
  }).catch(()=>this.fail('Recording upload failed. Keep the local copy; interview paused.')).finally(()=>{this.queuedBytes-=blob.size;});
 }
 // Analyser taps are read-only branches and never change the recording mix.
 meter(){
  const analyser=this.context?.createAnalyser?.();
  if(!analyser)return null;
  analyser.fftSize=256;analyser.smoothingTimeConstant=.65;analyser.minDecibels=-85;analyser.maxDecibels=-20;
  return analyser;
 }
 meterFor(kind){return kind==='question'?this.questionMeter:this.voiceMeter;}
 routeQuestion(audio){
  if(!this.context||!this.mix||this.state!=='recording')throw Error('Recording is not ready for question playback.');
  const source=this.context.createMediaElementSource(audio);source.connect(this.mix);source.connect(this.context.destination);this.sources.add(source);
  if(this.questionMeter)source.connect(this.questionMeter);
  return ()=>{try{source.disconnect();}catch{}this.sources.delete(source);};
 }
 pause(){
  if(this.state==='permission'){this.stop();return;}
  if(this.state!=='recording')return;
  this.recorder.pause();this.stream.getTracks().forEach(t=>t.enabled=false);this.notify('paused');
 }
 resume(){
  if(this.state!=='paused')throw Error('Recording cannot resume.');
  if(this.stream.getTracks().some(t=>t.readyState!=='live'))throw Error('A recording device was disconnected.');
  this.stream.getTracks().forEach(t=>t.enabled=true);this.recorder.resume();this.lastTick=performance.now();this.notify('recording');
 }
 fail(message){if(this.failed)return;this.failed=true;this.onFailure(message);this.stop();}
 async stop(){
  if(this.stopPromise)return this.stopPromise;
  this.generation++;clearInterval(this.timer);
  if(!this.recorder||this.recorder.state==='inactive'){await this.release();if(this.state==='permission')this.notify('cancelled');return null;}
  this.stopPromise=this.finished;this.notify('uploading');this.recorder.stop();this.stream?.getTracks().forEach(t=>{t.onended=null;t.stop();});return this.stopPromise;
 }
 async finalize(){
  this.blob=new Blob(this.parts,{type:this.mime});await this.queue;
  try{
   if(this.failed)throw Error('Incomplete recording');
   await this.api('/recordings/'+this.id+'/finish',{chunks:this.index});this.notify('saved');
  }catch{this.failed=true;await this.api('/recordings/'+this.id+'/abort',{}).catch(()=>{});this.notify('failed');}
  finally{await this.release();this.resolveFinished?.({id:this.id,blob:this.blob,complete:!this.failed});}
 }
 async release(){
  clearInterval(this.timer);this.stream?.getTracks().forEach(t=>{t.onended=null;t.stop();});
  for(const source of this.sources){try{source.disconnect();}catch{}}this.sources.clear();
  try{this.microphone?.disconnect();}catch{}
  for(const meter of [this.voiceMeter,this.questionMeter]){try{meter?.disconnect();}catch{}}
  this.voiceMeter=null;this.questionMeter=null;this.speechWorkletReady=false;
  if(this.context&&this.context.state!=='closed')await this.context.close();
 }
}
