// 16kHz mono PCM only. AudioContext is explicitly checked by the caller.
class InterviewPCM extends AudioWorkletProcessor {
 constructor(){super();this.buffer=new Int16Array(320);this.offset=0;}
 process(inputs){
  const channel=inputs[0]?.[0];if(!channel)return true;
  for(let i=0;i<channel.length;i++){
   const x=Math.max(-1,Math.min(1,channel[i]));this.buffer[this.offset++]=x<0?x*32768:x*32767;
   if(this.offset===320){const data=this.buffer.buffer;this.port.postMessage(data,[data]);this.buffer=new Int16Array(320);this.offset=0;}
  }
  return true;
 }
}
registerProcessor('interview-pcm',InterviewPCM);
