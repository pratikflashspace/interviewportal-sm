// Local preview only: no MediaRecorder, provider connection, upload or API calls.
export class DeviceCheck {
 constructor({devices=globalThis.navigator?.mediaDevices,Context=globalThis.AudioContext,Recorder=globalThis.MediaRecorder}={}){Object.assign(this,{devices,Context,Recorder});this.generation=0;}
 async open(){
  await this.close();const generation=++this.generation;let stream,context;
  try{
   if(!this.devices?.getUserMedia||!this.Context||!this.Recorder)throw Error('This browser does not support the interview devices.');
   if(!['video/webm;codecs=vp8,opus','video/webm','video/mp4'].some(m=>this.Recorder.isTypeSupported(m)))throw Error('No supported recording format.');
   stream=await this.devices.getUserMedia({video:{width:{ideal:640},height:{ideal:480}},audio:{echoCancellation:true,noiseSuppression:true,channelCount:1}});
   if(generation!==this.generation)throw Error('Device check cancelled.');
   if(!stream.getVideoTracks().length||!stream.getAudioTracks().length)throw Error('Camera and microphone are both required.');
   context=new this.Context({sampleRate:16000});await context.resume();
   if(generation!==this.generation)throw Error('Device check cancelled.');
   if(context.sampleRate!==16000)throw Error('This browser cannot provide the required audio format.');
   this.stream=stream;this.context=context;this.source=context.createMediaStreamSource(stream);this.meter=context.createAnalyser();this.meter.fftSize=256;this.source.connect(this.meter);
   return stream;
  }catch(e){stream?.getTracks().forEach(t=>t.stop());if(context&&context.state!=='closed')await context.close();throw e;}
 }
 level(){if(!this.meter)return 0;const values=new Uint8Array(this.meter.fftSize);this.meter.getByteTimeDomainData(values);return Math.max(...values.map(x=>Math.abs(x-128)))/128;}
 tone(){
  if(!this.context||this.context.state!=='running')throw Error('Run device checks first.');
  const oscillator=this.context.createOscillator(),gain=this.context.createGain();oscillator.frequency.value=440;gain.gain.value=.08;oscillator.connect(gain);gain.connect(this.context.destination);oscillator.start();oscillator.stop(this.context.currentTime+.4);oscillator.onended=()=>{oscillator.disconnect();gain.disconnect();};
 }
 async close(){this.generation++;this.stream?.getTracks().forEach(t=>t.stop());this.stream=null;this.source?.disconnect();this.meter?.disconnect();this.meter=null;if(this.context&&this.context.state!=='closed')await this.context.close();this.context=null;}
}
