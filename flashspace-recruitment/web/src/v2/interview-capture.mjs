// Capture belongs to ONE application and spans its questions, not a site-wide dock.
export class InterviewCapture {
 constructor({api,upload,mediaDevices=globalThis.navigator?.mediaDevices,Context=globalThis.AudioContext,Recorder=globalThis.MediaRecorder,Stream=globalThis.MediaStream,onChange=()=>{},onFailure=()=>{}}){
  Object.assign(this,{api,upload,mediaDevices,Context,Recorder,Stream,onChange,onFailure});
  this.state='idle';this.generation=0;this.parts=[];this.bytes=0;this.index=0;this.queue=Promise.resolve();this.failed=false;this.stopPromise=null;
 }
 notify(state){this.state=state;this.onChange({state,bytes:this.bytes,id:this.id,blob:this.blob});}
 async begin(applicationId,consent){
  if(!consent)throw Error('Camera and audio recording consent is required.');
  if(!['idle','failed','saved'].includes(this.state))throw Error('Recording is already active.');
  const generation=++this.generation;this.notify('permission');
  let stream;
  try{
   stream=await this.mediaDevices.getUserMedia({video:{width:{ideal:640},height:{ideal:480},frameRate:{ideal:15,max:20}},audio:{echoCancellation:true,noiseSuppression:true,channelCount:1}});
   if(generation!==this.generation){stream.getTracks().forEach(t=>t.stop());throw Error('Interview start cancelled.');}
   if(!stream.getVideoTracks().length||!stream.getAudioTracks().length)throw Error('Camera and microphone are both required.');
   this.stream=stream;this.context=new this.Context({sampleRate:16000});
   if(this.context.sampleRate!==16000)throw Error('This browser cannot provide 16 kHz interview audio.');
   await this.context.resume();this.mix=this.context.createMediaStreamDestination();
   this.microphone=this.context.createMediaStreamSource(new this.Stream(stream.getAudioTracks()));this.microphone.connect(this.mix);
   const mime=['video/webm;codecs=vp8,opus','video/webm','video/mp4'].find(t=>this.Recorder.isTypeSupported(t));
   if(!mime)throw Error('No compatible recording format.');
   const slot=await this.api('/v2/applications/'+applicationId+'/recording',{consent:'integrated-interview-av-v1',mime:mime.split(';')[0]});
   if(generation!==this.generation)throw Error('Interview start cancelled.');
   this.id=slot.id;this.applicationId=applicationId;this.parts=[];this.bytes=0;this.index=0;this.failed=false;this.queue=Promise.resolve();this.stopPromise=null;this.blob=null;
   this.limit=slot.max_bytes;this.remainingSeconds=slot.max_seconds;this.activeMs=0;this.lastTick=performance.now();
   const combined=new this.Stream([...stream.getVideoTracks(),...this.mix.stream.getAudioTracks()]);
   this.recorder=new this.Recorder(combined,{mimeType:mime,videoBitsPerSecond:350000,audioBitsPerSecond:48000});
   this.mime=mime;
   this.finished=new Promise(resolve=>{this.resolveFinished=resolve;});
   this.recorder.ondataavailable=e=>this.acceptChunk(e.data);
   this.recorder.onerror=()=>this.fail('Recording device error; interview paused.');
   this.recorder.onstop=()=>this.finalize();
   stream.getTracks().forEach(t=>t.onended=()=>{if(['recording','paused'].includes(this.state))this.fail('Camera or microphone disconnected; interview paused.');});
   this.recorder.start(2000);this.notify('recording');
   this.timer=setInterval(()=>{const now=performance.now();if(this.state==='recording')this.activeMs+=now-this.lastTick;this.lastTick=now;if(this.activeMs>=this.remainingSeconds*1000)this.fail('Temporary recording time limit reached. Interview paused; captured part is available for download.');},1000);
   return stream;
  }catch(e){stream?.getTracks().forEach(t=>t.stop());await this.release();this.notify('failed');throw e;}
 }
 acceptChunk(blob){
  if(!blob?.size)return;
  if(this.bytes+blob.size>this.limit){this.fail('Recording storage limit reached; captured portion is incomplete.');return;}
  this.bytes+=blob.size;this.parts.push(blob);
  this.queue=this.queue.then(async()=>{
   if(this.failed)return;
   for(let offset=0;offset<blob.size;offset+=1048576){
    const chunk=blob.slice(offset,offset+1048576);let success=false;
    for(let attempt=0;attempt<3&&!success;attempt++){
     try{await this.upload(this.id,this.index,chunk);success=true;}catch(e){if(attempt===2)throw e;await new Promise(r=>setTimeout(r,500*(attempt+1)));}
    }
    this.index++;
   }
  }).catch(()=>this.fail('Recording upload failed. Keep the local copy; interview paused.'));
 }
 routeQuestion(audio){
  if(!this.context||!this.mix)throw Error('Recording is not ready.');
  const source=this.context.createMediaElementSource(audio);source.connect(this.mix);source.connect(this.context.destination);
  return ()=>{try{source.disconnect();}catch{}};
 }
 pause(){
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
  if(!this.recorder||this.recorder.state==='inactive'){await this.release();return null;}
  this.stopPromise=this.finished;
  this.notify('uploading');this.recorder.stop();this.stream?.getTracks().forEach(t=>{t.onended=null;t.stop();});
  return this.stopPromise;
 }
 async finalize(){
  this.blob=new Blob(this.parts,{type:this.mime});
  await this.queue;
  try{
   if(this.failed)throw Error('Incomplete recording');
   await this.api('/recordings/'+this.id+'/finish',{chunks:this.index});this.notify('saved');
  }catch{this.failed=true;this.notify('failed');}
  await this.release();this.resolveFinished?.({id:this.id,blob:this.blob,complete:!this.failed});
 }
 async release(){
  clearInterval(this.timer);this.stream?.getTracks().forEach(t=>{t.onended=null;t.stop();});
  try{this.microphone?.disconnect();}catch{}
  if(this.context&&this.context.state!=='closed')await this.context.close();
 }
}
