// One interview voice channel: microphone, meters, question routing, speech worklet.
// Voice-only interviews: no camera, MediaRecorder, recording upload or storage.
// Historic A/V recordings remain readable; new capture is not attempted.
export class InterviewVoice {
 constructor({mediaDevices=globalThis.navigator?.mediaDevices,Context=globalThis.AudioContext,Stream=globalThis.MediaStream,onChange=()=>{},onFailure=()=>{}}){
  Object.assign(this,{mediaDevices,Context,Stream,onChange,onFailure});
  this.state='idle';this.generation=0;this.failed=false;this.sources=new Set();
 }
 notify(state){this.state=state;this.onChange({state});}
 assertCurrent(generation){if(generation!==this.generation)throw Error('Interview start cancelled.');}
 async prepareSpeechWorklet(){
  if(this.speechWorkletReady)return;
  if(!this.context?.audioWorklet)throw Error('This browser does not support live interview audio processing.');
  let timer;
  try{await Promise.race([this.context.audioWorklet.addModule('/v2-pcm-worklet.js'),new Promise((_,reject)=>{timer=setTimeout(()=>reject(Error('Audio processing setup timed out. No interview recording was started.')),10000);})]);this.speechWorkletReady=true;}
  finally{clearTimeout(timer);}
 }
 async begin(){
  if(!['idle','failed','cancelled','stopped'].includes(this.state))throw Error('Interview audio is already active.');
  this.voiceMeter=null;this.questionMeter=null;this.failed=false;
  const generation=++this.generation;this.notify('permission');let stream;
  try{
   stream=await this.mediaDevices.getUserMedia({audio:{echoCancellation:true,noiseSuppression:true,channelCount:1}});
   this.assertCurrent(generation);
   if(!stream.getAudioTracks().length)throw Error('A microphone is required for this voice interview.');
   this.stream=stream;this.context=new this.Context({sampleRate:16000});
   if(this.context.sampleRate!==16000)throw Error('This browser cannot provide 16 kHz interview audio.');
   await this.context.resume();this.assertCurrent(generation);
   // Complete worklet registration before connecting the listening graph, so a
   // stalled addModule cannot leave a live microphone attached to an idle interview.
   if(this.context.audioWorklet){await this.prepareSpeechWorklet();this.assertCurrent(generation);}
   this.mix=this.context.createMediaStreamDestination();
   this.microphone=this.context.createMediaStreamSource(new this.Stream(stream.getAudioTracks()));this.microphone.connect(this.mix);
   this.voiceMeter=this.meter();this.questionMeter=this.meter();
   if(this.voiceMeter)this.microphone.connect(this.voiceMeter);
   stream.getTracks().forEach(t=>t.onended=()=>{if(this.state==='live')this.fail('Microphone disconnected; interview paused.');});
   this.assertCurrent(generation);this.notify('live');
   return stream;
  }catch(e){
   stream?.getTracks().forEach(t=>t.stop());await this.release();
   this.notify(generation===this.generation?'failed':'cancelled');throw e;
  }
 }
 // Analyser taps are read-only branches and never change the listening graph.
 meter(){
  const analyser=this.context?.createAnalyser?.();
  if(!analyser)return null;
  analyser.fftSize=256;analyser.smoothingTimeConstant=.65;analyser.minDecibels=-85;analyser.maxDecibels=-20;
  return analyser;
 }
 meterFor(kind){return kind==='question'?this.questionMeter:this.voiceMeter;}
 routeQuestion(audio){
  if(!this.context||this.state!=='live')throw Error('Interview audio is not ready for question playback.');
  const source=this.context.createMediaElementSource(audio);source.connect(this.mix);source.connect(this.context.destination);this.sources.add(source);
  if(this.questionMeter)source.connect(this.questionMeter);
  return ()=>{try{source.disconnect();}catch{}this.sources.delete(source);};
 }
 fail(message){if(this.failed)return;this.failed=true;this.onFailure(message);this.stop();}
 async stop(){
  this.generation++;
  this.stream?.getTracks().forEach(t=>{t.onended=null;t.stop();});
  await this.release();
  this.notify(this.failed?'failed':'stopped');
  return null;
 }
 async release(){
  this.stream?.getTracks().forEach(t=>{t.onended=null;t.stop();});
  for(const source of this.sources){try{source.disconnect();}catch{}}
  this.sources.clear();
  try{this.microphone?.disconnect();}catch{}
  for(const meter of [this.voiceMeter,this.questionMeter]){try{meter?.disconnect();}catch{}}
  this.voiceMeter=null;this.questionMeter=null;this.speechWorkletReady=false;
  if(this.context&&this.context.state!=='closed')await this.context.close();
 }
}
