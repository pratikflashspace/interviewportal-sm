// Real Chromium + real local ASGI/SQL; synthetic provider boundaries only.
import {spawn,spawnSync} from 'node:child_process';
import {setTimeout as delay} from 'node:timers/promises';
import {mkdtempSync,writeFileSync,rmSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {chromium} from 'playwright';
import assert from 'node:assert/strict';
if(process.env.GITHUB_ACTIONS!=='true'){console.log('Browser integration skipped outside GitHub Actions.');process.exit(0);}
if(process.env.DATABASE_URL||process.env.CLICKUP_API_TOKEN||process.env.SARVAM_API_KEY)throw Error('CI fixture must not have live provider/database secrets.');
function run(cmd,args){const r=spawnSync(cmd,args,{stdio:'inherit'});if(r.status!==0)throw Error('Integration dependency setup failed: '+cmd);}
run('python',['-m','pip','install','-r','../requirements.txt']);run('npx',['playwright','install','--with-deps','chromium']);
// Chromium's default fake microphone can be silent after noise suppression.
// Feed a real PCM WAV through getUserMedia instead of faking the meter/check.
// This tests actual browser capture, resampling and preflight signal detection;
// it does not pretend that synthetic audio validates Sarvam transcription.
const fixtureDir=mkdtempSync(join(tmpdir(),'teamrecrut-media-'));
const microphone=join(fixtureDir,'microphone.wav'),rate=48000,samples=rate*4;
const wav=Buffer.alloc(44+samples*2);wav.write('RIFF',0);wav.writeUInt32LE(wav.length-8,4);wav.write('WAVEfmt ',8);wav.writeUInt32LE(16,16);wav.writeUInt16LE(1,20);wav.writeUInt16LE(1,22);wav.writeUInt32LE(rate,24);wav.writeUInt32LE(rate*2,28);wav.writeUInt16LE(2,32);wav.writeUInt16LE(16,34);wav.write('data',36);wav.writeUInt32LE(samples*2,40);
for(let i=0;i<samples;i++){const t=i/rate,envelope=.5+.5*Math.sin(2*Math.PI*3*t);const value=envelope*(Math.sin(2*Math.PI*180*t)+.4*Math.sin(2*Math.PI*370*t)+.2*Math.sin(2*Math.PI*730*t));wav.writeInt16LE(Math.round(10000*value),44+i*2);}writeFileSync(microphone,wav);
const server=spawn('python',['integration/server.py'],{stdio:'inherit',env:{...process.env,CI:'true'}});
let browser,page;const networkErrors=[];let phase='server';const origin='http://127.0.0.1:8765';
try{
 let healthy=false;for(let i=0;i<60;i++){try{if((await fetch(origin+'/api/health')).ok){healthy=true;break;}}catch{}await delay(500);}assert(healthy,'ASGI fixture starts');
 browser=await chromium.launch({headless:true,args:['--use-fake-ui-for-media-stream','--use-fake-device-for-media-stream','--use-file-for-fake-audio-capture='+microphone,'--disable-audio-track-processing','--autoplay-policy=no-user-gesture-required']});
 const context=await browser.newContext({permissions:['camera','microphone'],viewport:{width:1440,height:1000}});page=await context.newPage();page.setDefaultTimeout(20000);const errors=[];page.on('pageerror',e=>errors.push(e.message));page.on('response',r=>{if(r.status()>=400)networkErrors.push(r.status()+' '+new URL(r.url()).pathname);});
 phase='signup';await page.goto(origin+'/candidate/signup');
 await page.getByLabel('Full name',{exact:true}).fill('Synthetic Browser Candidate');await page.getByLabel('Email address',{exact:true}).fill('browser-candidate@example.com');await page.getByLabel('Password',{exact:true}).fill('synthetic-browser-password-123');await page.getByLabel('Confirm password',{exact:true}).fill('synthetic-browser-password-123');await page.getByRole('button',{name:'Create candidate account',exact:true}).click();await page.waitForURL('**/candidate/workspace/dashboard');
 phase='profile-save';await page.locator('.tr-main>header').getByRole('link',{name:'My Profile',exact:true}).click();await page.getByLabel(/Professional summary/).fill('Synthetic browser integration profile.');await page.getByRole('button',{name:'Save profile',exact:true}).click();await page.getByRole('status').filter({hasText:'Profile saved.'}).waitFor();
 phase='profile-reload';await page.reload();assert.equal(await page.getByLabel(/Professional summary/).inputValue(),'Synthetic browser integration profile.');
 phase='apply';await page.goto(origin+'/candidate/workspace/jobs');await page.getByRole('button',{name:'View role',exact:false}).first().click();await page.getByRole('button',{name:'Apply for this role',exact:true}).click();await page.getByLabel('Relevant experience',{exact:true}).fill('Synthetic browser test with relevant project experience.');await page.locator('#consent').click();await page.getByRole('button',{name:'Apply & start interview',exact:true}).click();await page.waitForURL('**/interview-v2?application=*');const aid=new URL(page.url()).searchParams.get('application');
 phase='preflight';await page.getByRole('button',{name:'Begin interview',exact:true}).waitFor();assert(await page.getByRole('button',{name:'Begin interview',exact:true}).isDisabled());
 for(const name of ['Pause interview','Use typing alternative'])assert.equal(await page.getByRole('button',{name,exact:true}).count(),0);assert.equal(await page.locator('text=10 core questions').count(),0);
 let raw=await page.evaluate(async aid=>(await fetch('/api/v2/applications/'+aid)).json(),aid);assert.equal(await page.getByText(raw.active.text,{exact:true}).count(),0,'Question not disclosed before speech');
 const recordings=()=>page.evaluate(async aid=>(await (await fetch('/api/v2/applications/'+aid+'/recordings')).json()).recordings,aid);
 assert.equal((await recordings()).length,0);
 await page.getByRole('button',{name:'Check camera and microphone',exact:true}).click();await page.getByText('Camera connected · Microphone signal detected',{exact:true}).waitFor();await page.getByRole('button',{name:'Play test sound',exact:true}).click();await page.getByLabel('I heard the test sound.').check();await page.getByLabel('I can see my camera preview.').check();await page.getByLabel('I consent to the described recording and processing.').check();assert.equal((await recordings()).length,0,'Device check creates no recording');
 await page.setViewportSize({width:390,height:844});assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),'Mobile room fits');await page.setViewportSize({width:1440,height:1000});
 phase='interview';await page.getByRole('button',{name:'Begin interview',exact:true}).click();await page.getByText('Recording this interview',{exact:true}).waitFor();
 await page.waitForFunction(()=>document.querySelector('.room-state')?.textContent==='Interview submitted',{},{timeout:210000});raw=await page.evaluate(async aid=>(await fetch('/api/v2/applications/'+aid)).json(),aid);assert.equal(raw.answers.length,10);assert.equal(raw.status,'completed');assert.equal(await page.locator('.room-error').count(),0);assert.equal(errors.length,0,errors.join('\n'));
 phase='recruiter';const recruiter=await browser.newContext({viewport:{width:1440,height:1000}}),review=await recruiter.newPage();review.setDefaultTimeout(20000);await review.goto(origin+'/recruiter/login');await review.getByLabel('Work email',{exact:true}).fill('team@stirringminds.com');await review.getByLabel('Password',{exact:true}).fill('synthetic-browser-password-123');await review.getByRole('button',{name:'Sign in',exact:true}).click();await review.waitForURL('**/recruiter/workspace/dashboard');
 const results=await review.evaluate(async aid=>{const records=await(await fetch('/api/admin/applications/'+aid+'/recordings')).json();const report=await(await fetch('/api/admin/v2/reports/'+aid)).json();const media=await fetch('/api/recordings/'+records.recordings[0].id+'/media');return {recordings:records.recordings.length,recordingStatus:records.recordings[0].status,bytes:(await media.arrayBuffer()).byteLength,report:report.report,sync:report.sync_status};},aid);
 assert.equal(results.recordings,1);assert.equal(results.recordingStatus,'ready');assert(results.bytes>1000);assert.equal(results.report.scoring_status,'not_scored');assert.equal(results.sync,'Synced');
 await review.goto(origin+'/interview-review?application='+aid);await review.waitForFunction(()=>document.querySelector('video'));await review.waitForFunction(()=>document.querySelector('video')?.videoWidth>0);
 assert.equal(await page.evaluate(async()=>(await fetch('/api/admin/applications')).status),403);
 console.log('PASS: Chromium + ASGI/WSGI + SQLite: signup, profile persistence, Apply, no pre-Begin recording, device checks, no early question DOM, mobile fit, automatic ten-answer interview, MediaRecorder upload and private video decoding, evidence report, mocked ClickUp sync, recruiter login and candidate access rejection. Sarvam/ClickUp boundaries synthetic.');
}catch(e){
 const body=page&&!page.isClosed()?await page.locator('body').innerText().catch(()=>'unavailable'):'';
 const message=JSON.stringify({phase,url:page?.url(),body:body.slice(0,2000),networkErrors:networkErrors.slice(-10),error:e.message}).replaceAll('%','%25').replaceAll('\n','%0A').replaceAll('\r','%0D');console.error('::error::SYNTHETIC_BROWSER_CONTEXT '+message);throw e;
}finally{await browser?.close();server.kill('SIGTERM');rmSync(fixtureDir,{recursive:true,force:true});}
