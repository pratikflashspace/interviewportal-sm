// CI-only native worklet probes; synthetic local fixture only.
import {chromium} from 'playwright';
if(process.env.GITHUB_ACTIONS==='true'){
 const launch=chromium.launch.bind(chromium);
 chromium.launch=async(...args)=>{
  const browser=await launch(...args),context=await browser.newContext(),page=await context.newPage();
  await page.goto('http://127.0.0.1:8765/api/health');
  const probes=await page.evaluate(async()=>{
   const source=await(await fetch('/v2-pcm-worklet.js')).text();const results=[];
   for(const mode of ['url-default','blob-default','blob-16000','suspended-url','offline-blob']){
    const ctx=mode==='offline-blob'?new OfflineAudioContext(1,16000,16000):new AudioContext(mode==='blob-16000'?{sampleRate:16000}:{});
    const url=mode.includes('blob')?URL.createObjectURL(new Blob([source],{type:'application/javascript'})):'/v2-pcm-worklet.js';let timer;
    try{if(!mode.startsWith('offline')&&!mode.startsWith('suspended'))await ctx.resume();const outcome=await Promise.race([ctx.audioWorklet.addModule(url).then(()=>{new AudioWorkletNode(ctx,'interview-pcm');return 'loaded-and-node-created';},e=>'error:'+e.name),new Promise(r=>{timer=setTimeout(()=>r('timeout'),2500);})]);results.push({mode,outcome,rate:ctx.sampleRate});}
    finally{clearTimeout(timer);if(ctx.close)await ctx.close();if(mode.includes('blob'))URL.revokeObjectURL(url);}
   }
   return results;
  });
  console.error('::notice::NATIVE_WORKLET_PROBES '+JSON.stringify(probes));await context.close();return browser;
 };
}
function safe(error){let text=String(error?.message||error).replaceAll('\n',' ').replaceAll('\r',' ');for(const [k,v] of Object.entries(process.env)){if(/TOKEN|SECRET|PASSWORD|DATABASE_URL|API_KEY/i.test(k)&&v.length>3)text=text.split(v).join('[REDACTED]');}return text.slice(0,1200).replaceAll('%','%25');}
try{await import('./run.mjs');}catch(e){console.error('::error::BROWSER_INTEGRATION_FAILURE '+safe(e));process.exitCode=1;}
