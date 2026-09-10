// Live speaking indicator for whoever currently holds the turn.
// Bars are read from an AnalyserNode on a rAF loop and written straight to the
// DOM as transforms: a talking head must never cost React a render per frame.
import React,{useEffect,useRef} from 'react';

const BARS=32;
// A resting shape, so the strip reads as an instrument rather than a dead row
// before the first sample arrives.
const REST=Array.from({length:BARS},(_,i)=>0.10+0.06*Math.sin(i/BARS*Math.PI*2));

export default function VoiceVisualizer({getMeter,active,tone='candidate',label=''}){
 const bars=useRef([]),meter=useRef(getMeter);
 meter.current=getMeter;
 useEffect(()=>{
  // Honour reduced motion by leaving the bars in their CSS resting state.
  if(typeof matchMedia==='function'&&matchMedia('(prefers-reduced-motion: reduce)').matches)return;
  let frame=0,data=null;const levels=new Float32Array(BARS);
  const draw=()=>{
   const node=active?meter.current?.():null;
   if(node){
    if(!data||data.length!==node.frequencyBinCount)data=new Uint8Array(node.frequencyBinCount);
    node.getByteFrequencyData(data);
    // Speech sits low in a 16 kHz graph; spread the bars across the bins that
    // carry voice instead of the near-silent top of the spectrum.
    const usable=Math.max(8,Math.floor(data.length*0.62));
    for(let i=0;i<BARS;i++){
     const from=Math.floor(i*usable/BARS),to=Math.max(from+1,Math.floor((i+1)*usable/BARS));
     let sum=0;for(let b=from;b<to;b++)sum+=data[b];
     const value=Math.min(1,sum/(to-from)/255*1.7);
     levels[i]=Math.max(value,levels[i]*0.86);
    }
   }else for(let i=0;i<BARS;i++)levels[i]*=0.82;
   for(let i=0;i<BARS;i++){
    const bar=bars.current[i];if(!bar)continue;
    bar.style.transform='scaleY('+(REST[i]+levels[i]*(1-REST[i])).toFixed(3)+')';
   }
   frame=requestAnimationFrame(draw);
  };
  frame=requestAnimationFrame(draw);
  return()=>cancelAnimationFrame(frame);
 },[active]);
 return <div className={'voice-viz voice-viz-'+tone+(active?' is-live':'')}>
  <div className="voice-viz-bars" aria-hidden="true">
   {Array.from({length:BARS},(_,i)=><span key={i} ref={n=>{bars.current[i]=n;}} style={{transform:'scaleY('+REST[i]+')'}}/>)}
  </div>
  {label&&<span className="voice-viz-label">{label}</span>}
 </div>;
}
