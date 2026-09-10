// CI-only real browser, synthetic devices and mocked APIs; no live secrets.
import {execFileSync} from 'node:child_process';
import fs from 'node:fs/promises';import os from 'node:os';import path from 'node:path';import http from 'node:http';import assert from 'node:assert/strict';
if(process.env.GITHUB_ACTIONS!=='true'){console.log('Browser acceptance runs in GitHub Actions; skipped on runtime/Render build.');process.exit(0);}
execFileSync(process.execPath,['node_modules/playwright/cli.js','install','chromium'],{stdio:'inherit'});
const {chromium}=await import('playwright');const {build}=await import('esbuild');
const temp=await fs.mkdtemp(path.join(os.tmpdir(),'interview-ui-'));
await build({stdin:{contents:`import React,{useState} from 'react';import {createRoot} from 'react-dom/client';import Interview from './src/IntegratedInterview.jsx';import Review from './src/InterviewRecordingReview.jsx';function Test(){const[a,setA]=useState({id:'test-app',role_title:'Fictional test role',status:'interview',answers:[],question:'Tell us about a fictional project.'});const[done,setDone]=useState(false);return location.pathname==='/review'?<Review applicationId="test-app"/>:done?<h1>Interview completed</h1>:<Interview application={a} onSaved={setA} onComplete={()=>setDone(true)} onBack={()=>setDone(true)}/>;}createRoot(document.getElementById('root')).render(<Test/>);`,resolveDir:process.cwd(),loader:'jsx'},bundle:true,outfile:path.join(temp,'test.js'),define:{'process.env.NODE_ENV':'"production"'}});
const js=await fs.readFile(path.join(temp,'test.js')),css=await fs.readFile(path.join(temp,'test.css'));
const server=http.createServer((req,res)=>{res.setHeader('Content-Type',req.url==='/test.js'?'application/javascript':req.url==='/test.css'?'text/css':'text/html');res.end(req.url==='/test.js'?js:req.url==='/test.css'?css:'<!doctype html><html><head><meta name="viewport" content="width=device-width,initial-scale=1"><link rel="stylesheet" href="/test.css"></head><body><div id="root"></div><script>window.__FLASHSPACE_LIVE__=true</script><script src="/test.js"></script></body></html>');});
await new Promise(r=>server.listen(0,'127.0.0.1',r));const origin='http://127.0.0.1:'+server.address().port;
const browser=await chromium.launch({headless:true,args:['--no-sandbox','--use-fake-ui-for-media-stream','--use-fake-device-for-media-stream','--autoplay-policy=no-user-gesture-required']});
const page=await browser.newPage({viewport:{width:1280,height:900},permissions:['camera','microphone']});
const errors=[];page.on('pageerror',e=>errors.push(e.message));let answers=[],chunks=0,finished=false,submitted=false;const requests=[];
function wav(){const n=1600,b=Buffer.alloc(44+n*2);b.write('RIFF');b.writeUInt32LE(b.length-8,4);b.write('WAVE',8);b.write('fmt ',12);b.writeUInt32LE(16,16);b.writeUInt16LE(1,20);b.writeUInt16LE(1,22);b.writeUInt32LE(16000,24);b.writeUInt32LE(32000,28);b.writeUInt16LE(2,32);b.writeUInt16LE(16,34);b.write('data',36);b.writeUInt32LE(n*2,40);return b;}
await page.route('**/api/**',async route=>{const req=route.request(),p=new URL(req.url()).pathname;requests.push(p);let value={};
 if(p==='/api/recordings'){const data=req.postDataJSON();assert.equal(data.application_id,'test-app');assert.equal(data.consent,'temporary-av-v1');value={id:'a'.repeat(32)};}
 else if(p.includes('/chunk/')){chunks++;value={chunks};}
 else if(p.startsWith('/api/recordings/')&&p.endsWith('/finish')){assert.ok(chunks>0);finished=true;value={status:'ready'};}
 else if(p.endsWith('/speech'))return route.fulfill({contentType:'audio/wav',body:wav()});
 else if(p.endsWith('/transcribe'))value={text:'I completed a fictional test project and measured its results.'};
 else if(p.endsWith('/turn-ready'))value={complete:true};
 else if(p.endsWith('/answer')){const data=req.postDataJSON();assert.equal(data.turn,answers.length);answers.push({question:'Fictional question',answer:data.answer});value={id:'test-app',role_title:'Fictional test role',status:'interview',answers,question:answers.length<4?'What did you learn from the fictional project?':null};}
 else if(p==='/api/applications/test-app/finish'){assert.ok(finished,'upload must finish before interview submission');assert.equal(answers.length,4);submitted=true;value={id:'test-app',status:'completed',answers};}
 else if(p==='/api/applications/test-app/recordings')value={recordings:[{id:'a'.repeat(32),status:'ready',created_at:new Date().toISOString(),mime:'video/webm'}]};
 else return route.fulfill({status:404,contentType:'application/json',body:JSON.stringify({error:'Unexpected API'})});
 return route.fulfill({contentType:'application/json',body:JSON.stringify(value)});
});
const listening=()=>page.getByRole('status').filter({hasText:'Listening — take your time'}).waitFor({timeout:20000});
try{
 await page.goto(origin);assert.equal(await page.locator('.recording-dock').count(),0);assert.equal(requests.length,0);
 await page.getByRole('checkbox').check();await page.getByRole('button',{name:'Begin / resume interview',exact:true}).click();await listening();
 const active=await page.locator('video').evaluate(v=>v.srcObject?.getVideoTracks()[0]?.readyState);assert.equal(active,'live');
 for(let i=0;i<4;i++){
  await listening();await page.locator('#interview-answer').fill('I completed a fictional project and measured its outcomes.');
  await page.getByRole('button',{name:'I’m finished answering'}).click();if(i<3)await page.getByText(`${i+1}/4 answers saved`,{exact:true}).waitFor();
 }
 await page.getByRole('heading',{name:'Interview completed',exact:true}).waitFor({timeout:20000});assert.ok(submitted);assert.ok(finished);assert.equal(requests.filter(x=>x==='/api/recordings').length,1);
 console.log('PASS application-bound Begin, camera/mixed audio, four turns, upload finalization, submission; no floating recorder');
 await page.goto(origin+'/review');await page.getByRole('heading',{name:'Interview recording'}).waitFor();await page.getByText('Segment 1 · ready').waitFor();assert.equal(await page.locator('video[controls]').count(),1);console.log('PASS application-specific recruiter recording panel');
 await page.setViewportSize({width:390,height:844});await page.goto(origin);await page.getByRole('status').filter({hasText:'Ready when you are'}).waitFor();assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);console.log('PASS narrow-screen layout');assert.deepEqual(errors,[]);
}catch(e){e.message+=' | SYNTHETIC UI: '+(await page.locator('body').innerText()).slice(0,4000)+' | requests: '+JSON.stringify(requests.slice(-20))+' | page errors: '+JSON.stringify(errors);throw e;}
finally{await browser.close();await new Promise(r=>server.close(r));await fs.rm(temp,{recursive:true,force:true});}
