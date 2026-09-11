// Approved Teamrecrut room: interviewer beside candidate, question below.
// Keep Manrope/Hind + violet/lilac. No per-answer recording, pause or typing UI.
import React,{useEffect,useRef,useState} from 'react';
import {TurnController} from './turn-controller.mjs';
import {InterviewCapture} from './interview-capture.mjs';
import {DraftClient} from './draft-client.mjs';
import {DeviceCheck} from './device-check.mjs';
import SpokenQuestion,{wordsOf,revealedAt} from './spoken-question.jsx';
import VoiceVisualizer from './voice-visualizer.jsx';
import '../generated/styles.css';
import '../RoleManager.css';
import './integrated-interview.css';
import './focused-room.css';
async function api(path,body,raw=false){
 const controller=new AbortController(),timeout=setTimeout(()=>controller.abort(),65000);
 try{const r=await fetch('/api'+path,{credentials:'same-origin',signal:controller.signal,method:body?'POST':'GET',headers:{'X-Requested-With':'Flashspace',...(body?{'Content-Type':'application/json'}:{})},...(body?{body:JSON.stringify(body)}:{})});if(!r.ok){let e;try{e=await r.json();}catch{}throw Error(e?.error||'Request failed. Your interview needs technical support.');}return raw?await r.blob():await r.json();}finally{clearTimeout(timeout);}
}
export default function IntegratedInterview(){
 const [user,setUser]=useState(undefined),[flow,setFlow]=useState(null),[consent,setConsent]=useState(false),[status,setStatus]=useState('ready'),[error,setError]=useState(''),[text,setText]=useState(''),[captureState,setCaptureState]=useState('idle'),[busy,setBusy]=useState(false),[playback,setPlayback]=useState(null),[downloads,setDownloads]=useState([]),[draftStatus,setDraftStatus]=useState(''),[orphans,setOrphans]=useState([]),[disclosure,setDisclosure]=useState({qid:null,count:0}),[started,setStarted]=useState(false),[help,setHelp]=useState(false),[devicesReady,setDevicesReady]=useState(false),[micDetected,setMicDetected]=useState(false),[heard,setHeard]=useState(false),[cameraConfirmed,setCameraConfirmed]=useState(false);
 const current=useRef(null),capture=useRef(null),video=useRef(null),speech=useRef(null),closing=useRef(Promise.resolve()),ctl=useRef(new TurnController()),epoch=useRef(0),paused=useRef(true),checking=useRef(false),saving=useRef(false),audio=useRef(null),timer=useRef(null),nextCheck=useRef(0),mounted=useRef(true),segmentBase=useRef(1),drafts=useRef(new DraftClient(api)),draftOwner=useRef(null),continuation=useRef(null),urls=useRef([]),startGuard=useRef(false),preflight=useRef(new DeviceCheck()),deviceTimer=useRef(null),played=useRef(new Map());
 useEffect(()=>{mounted.current=true;(async()=>{try{const u=await api('/me');if(!mounted.current)return;setUser(u);if(!u||u.admin)return;const aid=new URLSearchParams(location.search).get('application');if(!aid){setError('Open an interview from My Applications.');return;}const f=await api('/v2/applications/'+encodeURIComponent(aid));if(!mounted.current)return;current.current=f;setFlow(f);await restore(f);await allowance(f);const r=await api('/v2/applications/'+f.application_id+'/recordings');if(!mounted.current)return;setOrphans(r.recordings.filter(x=>x.status==='uploading'));setStatus(f.status==='completed'?'answers-completed':'ready');}catch(e){if(mounted.current)setError(e.message);}})();
 const unload=e=>{if(['permission','recording','paused','uploading'].includes(capture.current?.state)){e.preventDefault();e.returnValue='Recording or upload active.';}};window.addEventListener('beforeunload',unload);
 return()=>{mounted.current=false;paused.current=true;epoch.current++;clearInterval(timer.current);clearInterval(deviceTimer.current);preflight.current.close();closeSpeech();stopAudio();capture.current?.stop();drafts.current.invalidate();urls.current.forEach(URL.revokeObjectURL);window.removeEventListener('beforeunload',unload);};},[]);
 useEffect(()=>{if(video.current)video.current.srcObject=capture.current?.stream||preflight.current.stream||null;},[captureState,flow?.application_id,devicesReady]);
 useEffect(()=>{const f=current.current;if(!f?.active||draftOwner.current!==f.active.id||saving.current||continuation.current||text.length>6000)return;let cancelled=false;const t=setTimeout(async()=>{if(draftOwner.current!==f.active.id||saving.current)return;setDraftStatus('Saving draft…');try{const r=await drafts.current.save(f.application_id,f.active.id,text);if(!cancelled&&r)setDraftStatus('Draft saved; not yet submitted.');}catch(e){if(!cancelled){setDraftStatus('Draft not saved. Keep this tab open.');stopWithError(e.message);}}},1000);return()=>{cancelled=true;clearTimeout(t);};},[text,flow?.active?.id]);
 function paint(){if(mounted.current){setStatus(ctl.current.state);setText(ctl.current.transcript());}}
 function stopAudio(){const a=audio.current;audio.current=null;if(a){a.stopReveal?.();a.player.onended=null;a.player.onerror=null;a.player.pause();a.disconnect();URL.revokeObjectURL(a.url);a.resolve(false);}}
 function closeSpeech(){const s=speech.current;speech.current=null;if(!s)return closing.current;s.processor.port.onmessage=null;s.processor.disconnect();s.input.disconnect();s.silent.disconnect();s.socket.onmessage=null;s.socket.onerror=null;s.socket.onclose=null;s.cancel?.();closing.current=new Promise(resolve=>{if(s.socket.readyState===3)return resolve();const t=setTimeout(resolve,5500);s.socket.onclose=()=>{clearTimeout(t);resolve();};s.socket.close();});return closing.current;}
 function stopWithError(message){paused.current=true;epoch.current++;ctl.current.pause();stopAudio();capture.current?.pause();closeSpeech();clearInterval(timer.current);if(mounted.current){setStatus('technical-stop');setError(message);}}
 async function allowance(f=current.current){if(!f?.active){if(mounted.current)setPlayback(null);return null;}const p=await api('/v2/applications/'+f.application_id+'/playback');if(mounted.current&&current.current?.active?.id===p.question_id)setPlayback(p);return p;}
 async function restore(f){draftOwner.current=null;drafts.current.invalidate();if(mounted.current)setDisclosure({qid:f.active?.id,count:played.current.get(f.active?.id)||0});ctl.current.begin();ctl.current.pause();continuation.current=null;if(f.active){const d=await drafts.current.load(f.application_id,f.active.id);if(d?.transcript)ctl.current.segments.set(0,d.transcript);draftOwner.current=f.active.id;if(mounted.current){setText(d?.transcript||'');setDraftStatus(d?.transcript?'Saved draft restored.':'');}}else if(mounted.current)setText('');}
 async function checkDevices(){setBusy(true);setError('');setDevicesReady(false);setMicDetected(false);setHeard(false);setCameraConfirmed(false);clearInterval(deviceTimer.current);try{const stream=await preflight.current.open();if(!mounted.current)return;if(video.current)video.current.srcObject=stream;setDevicesReady(true);deviceTimer.current=setInterval(()=>{if(preflight.current.level()>.015)setMicDetected(true);},100);stream.getTracks().forEach(t=>t.onended=()=>{setDevicesReady(false);setError('A device disconnected. Run device checks again.');});}catch(e){if(mounted.current)setError(e.message);}finally{if(mounted.current)setBusy(false);}}
 function playTest(){try{preflight.current.tone();}catch(e){setError(e.message);}}
 function retryable(e){e.retryable=true;return e;}
 async function connectSpeech(){for(let attempt=0;;attempt++){try{return await openSpeech();}catch(e){if(!e.retryable||attempt>=2||paused.current)throw e;await closeSpeech();await new Promise(r=>setTimeout(r,400*(attempt+1)));if(paused.current)throw Error('Listening cancelled.');}}}
 async function openSpeech(){
  await closeSpeech();const media=capture.current,run=epoch.current;if(paused.current||media?.state!=='recording')throw Error('Interview stopped before listening started.');
  const base=segmentBase.current;segmentBase.current+=10001;await media.context.audioWorklet.addModule('/v2-pcm-worklet.js');if(paused.current||run!==epoch.current)throw Error('Listening cancelled.');
  const processor=new AudioWorkletNode(media.context,'interview-pcm'),input=media.context.createMediaStreamSource(new MediaStream(media.stream.getAudioTracks())),silent=media.context.createGain();silent.gain.value=0;input.connect(processor);processor.connect(silent);silent.connect(media.context.destination);
  const socket=new WebSocket((location.protocol==='https:'?'wss:':'ws:')+'//'+location.host+'/api/v2/voice/'+current.current.application_id);const state={socket,processor,input,silent};speech.current=state;
  processor.port.onmessage=e=>{if(!paused.current&&run===epoch.current&&socket.readyState===1){if(socket.bufferedAmount>64000){stopWithError('Voice network is behind. Capture has been stopped for technical review.');return;}socket.send(e.data);}};
  let live=false;
  await new Promise((resolve,reject)=>{const t=setTimeout(()=>reject(retryable(Error('Voice connection timed out.'))),20000);state.cancel=()=>{clearTimeout(t);reject(Error('Listening cancelled.'));};
   socket.onmessage=e=>{if(run!==epoch.current)return;let msg;try{msg=JSON.parse(e.data);}catch{return;}if(msg.event==='ready'){clearTimeout(t);state.cancel=null;live=true;resolve();return;}if(msg.event==='error'){clearTimeout(t);reject(Error(msg.message));stopWithError(msg.message);return;}if(paused.current)return;const index=base+msg.utterance_idx;
    if(msg.event==='vad.speech_start'){ctl.current.speechStart(index);stopAudio();}
    if(msg.event==='vad.speech_end')ctl.current.speechEnd();
    if(msg.event==='transcript.partial'){ctl.current.partial(index);stopAudio();}
    if(msg.event==='transcript.final')ctl.current.final(index,msg.text);
    if(ctl.current.transcript().length>6000){stopWithError('Answer exceeds the supported size. No text was silently truncated. Contact support.');return;}paint();
   };
   socket.onerror=()=>{clearTimeout(t);if(!live){reject(retryable(Error('Voice connection failed.')));return;}if(!paused.current)stopWithError('Voice connection failed. Contact support before continuing.');};
   socket.onclose=()=>{clearTimeout(t);if(!live){reject(retryable(Error('Voice connection failed.')));return;}if(!paused.current&&run===epoch.current)stopWithError('Voice connection lost. Camera and microphone capture are stopped.');};
  });
  if(paused.current||run!==epoch.current)throw Error('Listening cancelled.');
 }
 function trackReveal(player,text,qid){
  const total=wordsOf(text).length;if(!total)return null;let frame=0,last=-1;
  const step=()=>{const shown=revealedAt(player.currentTime,player.duration,total);if(shown!==last){last=shown;played.current.set(qid,shown);if(mounted.current)setDisclosure({qid,count:shown});}frame=requestAnimationFrame(step);};
  frame=requestAnimationFrame(step);return()=>cancelAnimationFrame(frame);
 }
 async function speak(introduction=false){
  const f=current.current,token=ctl.current.epoch,run=epoch.current;setStatus('processing');let blob;
  if(!introduction)setDisclosure({qid:f.active.id,count:0});
  try{blob=await api('/v2/applications/'+f.application_id+(introduction?'/intro':'/speech'),introduction?{}:{question_id:f.active.id},true);}finally{if(!introduction)await allowance();}
  if(paused.current||run!==epoch.current||!ctl.current.canPlay(token))return false;
  return new Promise(resolve=>{const url=URL.createObjectURL(blob),player=new Audio(url);let disconnect;try{disconnect=capture.current.routeQuestion(player);}catch(e){URL.revokeObjectURL(url);stopWithError(e.message);resolve(false);return;}
   const stopReveal=introduction?null:trackReveal(player,f.active?.text,f.active?.id);audio.current={player,url,disconnect,resolve,stopReveal};setStatus('ai-speaking');
   player.onended=()=>{stopReveal?.();disconnect();URL.revokeObjectURL(url);audio.current=null;if(run===epoch.current){if(!introduction){const count=wordsOf(f.active.text).length;played.current.set(f.active.id,count);setDisclosure({qid:f.active.id,count});ctl.current.playbackEnded(token);}paint();}resolve(true);};
   player.onerror=()=>{stopAudio();stopWithError('Question playback failed. Contact support; the interview has not been declared complete.');};player.play().catch(()=>{stopAudio();stopWithError('Browser blocked audio playback. Contact support before restarting.');});});
 }
 function checks(){clearInterval(timer.current);timer.current=setInterval(()=>{if(!paused.current&&!checking.current&&!saving.current&&ctl.current.ready()&&Date.now()>=nextCheck.current)endCheck();},300);}
 function captureFactory(){return new InterviewCapture({api,upload:async(rid,index,chunk)=>{const controller=new AbortController(),t=setTimeout(()=>controller.abort(),30000);try{const r=await fetch('/api/recordings/'+rid+'/chunk/'+index,{signal:controller.signal,method:'POST',credentials:'same-origin',headers:{'X-Requested-With':'Flashspace','Content-Type':'application/octet-stream'},body:chunk});if(!r.ok)throw Error('Recording upload failed.');}finally{clearTimeout(t);}},onChange:v=>{if(!mounted.current)return;setCaptureState(v.state);if(v.blob){const url=URL.createObjectURL(v.blob);urls.current.push(url);setDownloads(rows=>rows.some(r=>r.id===v.id)?rows:[...rows,{id:v.id,url,complete:v.state==='saved',extension:v.mime?.includes('mp4')?'mp4':'webm'}]);}},onFailure:stopWithError});}
 async function begin(){
  if(startGuard.current||saving.current||started||!consent||!devicesReady||!micDetected||!heard||!cameraConfirmed||orphans.length)return;
  startGuard.current=true;setStarted(true);setBusy(true);setError('');const run=++epoch.current;paused.current=false;
  try{
   clearInterval(deviceTimer.current);await preflight.current.close();
   const f=await api('/v2/applications/'+current.current.application_id);if(epoch.current!==run||paused.current)throw Error('Start cancelled.');
   current.current=f;setFlow(f);if(f.status==='completed'){paused.current=true;setStatus('answers-completed');return;}if(!f.active)throw Error('Next question is not ready. Contact support.');
   await drafts.current.chain;await restore(f);const prior=ctl.current.transcript();ctl.current.begin();if(prior)ctl.current.segments.set(0,prior);paused.current=false;
   capture.current=captureFactory();await capture.current.begin(f.application_id,true);
   if(epoch.current!==run||paused.current){capture.current.pause();throw Error('Start cancelled.');}
   if(video.current)video.current.srcObject=capture.current.stream;await connectSpeech();const p=await allowance(f);
   if(!f.answers.length&&!prior&&p.initial_available){const ok=await speak(true);if(!ok){stopWithError('Introduction was interrupted. Contact support.');return;}await closeSpeech();ctl.current.begin();await connectSpeech();}
   checks();if(!prior&&p.deliveries_remaining>0)await speak();else{ctl.current.state='listening';paint();}
  }catch(e){stopWithError(e.message);}finally{startGuard.current=false;if(mounted.current)setBusy(false);}
 }
 async function endCheck(){checking.current=true;const token=ctl.current.prepare();if(token===null){checking.current=false;return;}setStatus('processing');const f=current.current;
  try{if(continuation.current){await commitContinuation(token);return;}const result=await api('/v2/applications/'+f.application_id+'/end-check',{question_id:f.active.id,version:f.version,answer:ctl.current.transcript()});if(paused.current||!ctl.current.canPlay(token))return;if(!result.complete){ctl.current.state='end-pending';nextCheck.current=Date.now()+15000;paint();return;}await submit(ctl.current.transcript(),token);}catch(e){stopWithError(e.message);}finally{checking.current=false;}}
 async function advance(next){
  continuation.current=null;current.current=next;setFlow(next);await closeSpeech();await restore(next);setText('');
  if(next.status==='completed'){paused.current=true;epoch.current++;stopAudio();clearInterval(timer.current);setStatus('uploading');const saved=await capture.current?.stop();ctl.current.complete();setStatus(saved?.complete?'completed':'answers-completed');return;}
  if(paused.current){setStatus('technical-stop');await allowance(next);return;}
  ctl.current.begin();draftOwner.current=next.active.id;await connectSpeech();await allowance(next);await speak();checks();
 }
 async function commitContinuation(token){const info=continuation.current,answer=ctl.current.transcript();if(!info||saving.current)return;saving.current=true;setBusy(true);try{const f=current.current;if(f.status==='completed')throw Error('Additional final-answer speech needs recruiter reconciliation with the recording.');const next=await api('/v2/applications/'+f.application_id+'/continuation',{event_id:info.event_id,version:f.version,answer});current.current=next;setFlow(next);if(paused.current||!ctl.current.canPlay(token)){info.version=next.version;return;}await advance(next);}finally{saving.current=false;setBusy(false);}}
 async function submit(answer,token){
  if(saving.current||!answer.trim()||answer.length>6000)return;if(continuation.current){await commitContinuation(token);return;}
  const f=current.current,run=epoch.current,event=crypto.randomUUID();saving.current=true;setBusy(true);setStatus('saving');
  try{await drafts.current.chain;if(paused.current||!ctl.current.canPlay(token)){paint();return;}
   const next=await api('/v2/applications/'+f.application_id+'/answer',{event_id:event,version:f.version,question_id:f.active.id,answer});current.current=next;setFlow(next);drafts.current.invalidate();draftOwner.current=null;
   if(!ctl.current.canPlay(token)||ctl.current.transcript()!==answer){continuation.current={event_id:event,version:next.version};setDraftStatus('Waiting for your additional speech to finish.');if(next.status==='completed'){stopWithError('Speech resumed during final submission. Contact support for review; keep the recording.');return;}if(!paused.current){ctl.current.state=ctl.current.speaking?'candidate-speaking':'end-pending';paint();checks();}return;}
   if(paused.current||run!==epoch.current){await restore(next);setStatus(next.status==='completed'?'answers-completed':'technical-stop');if(next.status==='completed')await capture.current?.stop();return;}await advance(next);
  }catch(e){stopWithError(e.message+' Contact support before retrying an uncertain submission.');}finally{saving.current=false;setBusy(false);}
 }
 async function replay(){if(ctl.current.speaking||ctl.current.pending.size||busy||paused.current||continuation.current)return;setBusy(true);try{const p=await allowance();if(p.deliveries_remaining>0){ctl.current.epoch++;ctl.current.state='ai-speaking';await speak();}}catch(e){stopWithError(e.message);}finally{setBusy(false);}}
 async function leave(){if(busy)return;if(!confirm('Exit this interview? Submitted answers stay saved; an unfinished answer is not a submitted answer.'))return;setBusy(true);paused.current=true;epoch.current++;ctl.current.pause();stopAudio();await closeSpeech();clearInterval(timer.current);clearInterval(deviceTimer.current);try{await preflight.current.close();await drafts.current.chain;await capture.current?.stop();location.assign('/candidate/workspace/applications');}catch(e){setError('Could not finish saving: '+e.message);setStatus('technical-stop');}finally{setBusy(false);}}
 async function preserveRecording(){setBusy(true);try{await drafts.current.chain;await capture.current?.stop();}catch(e){setError(e.message);}finally{setBusy(false);}}
 const aiSpeaking=status==='ai-speaking',listening=['listening','candidate-speaking','end-pending'].includes(status),done=flow?.status==='completed';
 const label={'ready':'Ready when you are','ai-speaking':'Interviewer is speaking…','candidate-speaking':'Listening to you…','listening':'Listening…','end-pending':'Listening — take your time','processing':'Processing your response…','saving':'Saving your response…','uploading':'Finishing your recording…','completed':'Interview submitted','answers-completed':'Answers submitted — recording status below','technical-stop':'Technical interruption'}[status]||'Preparing interview…';
 const shown=disclosure.qid===flow?.active?.id?disclosure.count:0;
 return <main className="focused-room"><header><a href="/candidate/workspace/applications">teamrecrut · AI Interview</a><div><button onClick={()=>setHelp(!help)}>Help</button><button onClick={leave} disabled={busy}>Exit interview</button></div></header>
 {help&&<section className="room-help"><h2>Interview help</h2><p>Speak naturally and allow time for processing. Short pauses are not treated as completed answers. For a technical problem, use your in-app support inbox. No typing or free-pause mode is available here.</p><p>Recordings are temporary in this pilot. They may be lost on server replacement; consent details are shown before Begin.</p><a href="/candidate/workspace/help" target="_blank" rel="noopener noreferrer">Open Help & Support</a></section>}
 {error&&<p role="alert" className="room-error">{error}</p>}
 {user===undefined?<p>Checking interview access…</p>:!user?<p><a href="/candidate/login">Sign in as a candidate</a>, then open My Interviews.</p>:user.admin?<p>Candidate access is required. <a href="/recruiter/workspace/dashboard">Return to recruiter dashboard</a></p>:!flow?<p><a href="/candidate/workspace/applications">Open an application to enter its interview.</a></p>:<>
 <h1>Your experience, in your words.</h1>
 {!started&&!done&&<section className="room-preflight"><h2>Before you begin</h2><p>This is a voice conversation. The interviewer asks one question at a time and listens automatically. Device checks preview your camera and measure your microphone locally; they do not record, upload or contact the AI provider.</p><p>Your camera, microphone and interviewer audio will be recorded only after Begin. Sarvam processes interview audio/text; drafts and submitted answers are saved, and submitted records are sent to ClickUp for authorised human review. Pilot video storage is temporary: up to 10 recordings, 50 MB each; copies can disappear on server replacement. Use fictional data until a production retention policy is approved.</p><button onClick={checkDevices} disabled={busy}>Check camera and microphone</button><p role="status">{devicesReady?(micDetected?'Camera connected · Microphone signal detected':'Camera connected · Speak to test your microphone'):'Device checks not completed'}</p>{devicesReady&&<><button onClick={playTest}>Play test sound</button><label><input type="checkbox" checked={heard} onChange={e=>setHeard(e.target.checked)}/>I heard the test sound.</label><label><input type="checkbox" checked={cameraConfirmed} onChange={e=>setCameraConfirmed(e.target.checked)}/>I can see my camera preview.</label></>}
 <label><input type="checkbox" checked={consent} onChange={e=>setConsent(e.target.checked)}/>I consent to the described recording and processing.</label>{orphans.length>0&&<p role="alert">An earlier recording is unfinished. Contact support before starting another; this screen will not discard it.</p>}
 <button onClick={begin} disabled={busy||!devicesReady||!micDetected||!heard||!cameraConfirmed||!consent||orphans.length>0}>Begin interview</button></section>}
 <div className="room-participants"><section className="room-interviewer"><h2>AI interviewer</h2><VoiceVisualizer tone="interviewer" active={aiSpeaking} getMeter={()=>capture.current?.meterFor('question')} label={aiSpeaking?'Speaking':''}/><p>{aiSpeaking?'Speaking':'Here to listen'}</p></section><section className="room-candidate"><h2>You</h2><video ref={video} autoPlay muted playsInline aria-label="Your live camera preview"/><p>{captureState==='recording'?'Recording this interview':devicesReady&&!started?'Device preview — not recording':captureState==='paused'?'Capture stopped':captureState==='saved'?'Recording uploaded':captureState==='failed'?'Recording incomplete':'Camera inactive'}</p></section></div>
 {!done&&<section className="room-question"><SpokenQuestion text={flow.active?.text} revealed={shown}/></section>}
 <p className="room-state" role="status">{label}</p>
 {started&&!done&&status!=='technical-stop'&&<><VoiceVisualizer tone="candidate" active={listening} getMeter={()=>capture.current?.meterFor('voice')} label={listening?'Listening':''}/><button className="room-replay" disabled={busy||paused.current||aiSpeaking||!playback||playback.deliveries_remaining<=0||ctl.current.speaking||ctl.current.pending.size>0||!!continuation.current} onClick={replay}>Hear again ({playback?.replays_remaining??2} left)</button><section className="room-transcript"><h2>Your response</h2><p>{text||'Your speech transcript appears here.'}</p><small>{draftStatus}</small></section></>}
 {status==='technical-stop'&&<section className="room-help"><p>No answer has been silently resubmitted. Contact support; automatic retry after an uncertain submission requires a separately approved recovery flow.</p><button disabled={busy||captureState==='saved'} onClick={preserveRecording}>Save captured portion for support</button></section>}
 {done&&<p>Your saved answers are submitted for human review. {captureState==='saved'?'The current recording segment was uploaded.':captureState==='uploading'?'Keep this page open while the recording uploads.':'A complete recording has not been verified on this page.'}</p>}
 {(done||status==='technical-stop')&&downloads.map(d=><p key={d.id}><a download={'interview-'+d.id+'.'+d.extension} href={d.url}>Download captured {d.complete?'uploaded':'incomplete'} segment</a></p>)}
 </>}
 </main>;
}
