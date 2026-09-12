// CI-only native worklet regression; no production/provider traffic.
// Playwright 1.55.1 stalls addModule even on a bare page (upstream #37592).
import assert from 'node:assert/strict';
import {chromium} from 'playwright';
import {checkGoogleLogin} from './google-login.mjs';
import {installReportDiagnostics} from './report-diagnostics.mjs';
if(process.env.GITHUB_ACTIONS==='true'){
 const launch=chromium.launch.bind(chromium);
 chromium.launch=async(...args)=>{
  const browser=await launch(...args);let context;
  installReportDiagnostics(browser);
  try{
   context=await browser.newContext();const page=await context.newPage();
   await page.goto('http://127.0.0.1:8765/api/health');
   const result=await page.evaluate(async()=>{
    const response=await fetch('/v2-pcm-worklet.js');
    if(!response.ok)throw Error('Worklet route failed');
    const ctx=new AudioContext({sampleRate:16000});let timer,oscillator,node,silent;
    try{
     await ctx.resume();
     await Promise.race([ctx.audioWorklet.addModule('/v2-pcm-worklet.js'),new Promise((_,reject)=>{timer=setTimeout(()=>reject(Error('Native worklet module registration timed out')),3000);})]);clearTimeout(timer);
     node=new AudioWorkletNode(ctx,'interview-pcm');oscillator=ctx.createOscillator();silent=ctx.createGain();silent.gain.value=0;
     oscillator.connect(node);node.connect(silent);silent.connect(ctx.destination);
     const frame=new Promise((resolve,reject)=>{timer=setTimeout(()=>reject(Error('Native worklet produced no PCM frame')),3000);node.port.onmessage=e=>{clearTimeout(timer);const samples=new Int16Array(e.data);resolve({bytes:e.data.byteLength,nonzero:samples.some(x=>x!==0)});};});
     oscillator.start();const pcm=await frame;
     return {rate:ctx.sampleRate,...pcm};
    }finally{clearTimeout(timer);if(node)node.port.onmessage=null;try{oscillator?.stop();}catch{}oscillator?.disconnect();node?.disconnect();silent?.disconnect();await ctx.close();}
   });
   assert.equal(result.rate,16000);assert.equal(result.bytes,640);assert.equal(result.nonzero,true);
   console.log('PASS: native AudioWorklet loads and produces nonzero 16 kHz PCM frames before full browser integration.');
   await context.close();await checkGoogleLogin(browser);return browser;
  }catch(e){await context?.close();await browser.close();throw e;}
 };
}
function safe(error){let text=String(error?.message||error).replaceAll('\n',' ').replaceAll('\r',' ');for(const [k,v] of Object.entries(process.env)){if(/TOKEN|SECRET|PASSWORD|DATABASE_URL|API_KEY/i.test(k)&&v.length>3)text=text.split(v).join('[REDACTED]');}return text.slice(0,1200).replaceAll('%','%25');}
try{await import('./run.mjs');}catch(e){console.error('::error::BROWSER_INTEGRATION_FAILURE '+safe(e));process.exitCode=1;}
