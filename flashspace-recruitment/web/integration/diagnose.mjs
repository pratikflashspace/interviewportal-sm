// CI-only browser diagnostics. Static operation labels only; no credentials/audio.
import {chromium} from 'playwright';
const pages=[],requests=[];
if(process.env.GITHUB_ACTIONS==='true'){
 const launch=chromium.launch.bind(chromium);
 chromium.launch=async(...args)=>{
  const browser=await launch(...args),newContext=browser.newContext.bind(browser);
  browser.newContext=async(...args)=>{
   const context=await newContext(...args);
   await context.addInitScript(()=>{
    window.__mediaSetup=[];
    const mark=(name,value)=>{window.__mediaSetup.push([name,value]);if(window.__mediaSetup.length>60)window.__mediaSetup.shift();};
    const Original=window.AudioContext;
    if(Original)window.AudioContext=class extends Original{
     constructor(...args){super(...args);mark('context-created',this.sampleRate);this.addEventListener('statechange',()=>mark('context-state',this.state));const add=this.audioWorklet.addModule.bind(this.audioWorklet);this.audioWorklet.addModule=async(...a)=>{mark('worklet-start',true);try{const v=await add(...a);mark('worklet-loaded',true);return v;}catch(e){mark('worklet-failed',e.name);throw e;}};}
     async resume(){mark('context-resume',this.state);const v=await super.resume();mark('context-resumed',this.state);return v;}
    };
    const WS=window.WebSocket;
    window.WebSocket=class extends WS{constructor(...a){super(...a);mark('socket-created',true);this.addEventListener('open',()=>mark('socket-open',true));this.addEventListener('close',e=>mark('socket-close',e.code));this.addEventListener('message',e=>{try{const v=JSON.parse(e.data);if(['ready','error','vad.speech_start','vad.speech_end','transcript.final'].includes(v.event))mark('socket-event',v.event);}catch{}});}};
   });
   context.on('page',page=>{pages.push(page);page.on('response',r=>{const p=new URL(r.url()).pathname;const type=p.endsWith('/speech')?'speech':p.endsWith('/intro')?'intro':p.endsWith('/answer')?'answer':p.endsWith('/end-check')?'end-check':p.endsWith('v2-pcm-worklet.js')?'worklet':null;if(type){requests.push([type,r.status()]);if(requests.length>30)requests.shift();}});});
   return context;
  };
  // Capture before run.mjs closes the browser in its finally block.
  const close=browser.close.bind(browser);
  browser.close=async(...a)=>{for(const page of pages){if(!page.isClosed()){const data=await page.evaluate(()=>({media:window.__mediaSetup,room:document.querySelector('.room-state')?.textContent})).catch(()=>null);console.error('::notice::SYNTHETIC_MEDIA_SETUP '+JSON.stringify({data,requests}));}}return close(...a);};
  return browser;
 };
}
function safe(error){let text=String(error?.message||error).replaceAll('\n',' ').replaceAll('\r',' ');for(const [k,v] of Object.entries(process.env)){if(/TOKEN|SECRET|PASSWORD|DATABASE_URL|API_KEY/i.test(k)&&v.length>3)text=text.split(v).join('[REDACTED]');}return text.slice(0,1200).replaceAll('%','%25');}
try{await import('./run.mjs');}catch(e){console.error('::error::BROWSER_INTEGRATION_FAILURE '+safe(e));process.exitCode=1;}
