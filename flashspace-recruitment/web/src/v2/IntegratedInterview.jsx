// Approved Teamrecrut room: AI interviewer and candidate waveforms side by side.
// Voice-only: microphone check, one Begin, no camera, no recording UI.
// Button-driven turns: the microphone only listens after "Tap to speak" and
// closes at "I'm done speaking", so background noise can never interrupt the
// interviewer, and each answer ends on the candidate's explicit signal.
// Provider failures are recoverable, not fatal: TTS failure reveals the
// question text; a dropped voice socket keeps the transcript and offers
// reconnect-or-done. Only usage limits and failed answer submissions stop.
import React,{useEffect,useRef,useState} from 'react';
import {TurnController} from './turn-controller.mjs';
import {InterviewVoice} from './interview-capture.mjs';
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
 const [user,setUser]=useState(undefined),[flow,setFlow]=useState(null),[consent,setConsent]=useState(false),[status,setStatus]=useState('ready'),[error,setError]=useState(''),[warn,setWarn]=useState(''),[text,setText]=useState(''),[voiceState,setVoiceState]=useState('idle'),[busy,setBusy]=useState(false),[draftStatus,setDraftStatus]=useState(''),[disclosure,setDisclosure]=useState({qid:null,count:0}),[started,setStarted]=useState(false),[help,setHelp]=useState(false),[devicesReady,setDevicesReady]=useState(false),[micDetected,setMicDetected]=useState(false),[focusNote,setFocusNote]=useState('');
 const current=useRef(null),voice=useRef(null),speech=useRef(null),closing=useRef(Promise.resolve()),ctl=useRef(new TurnController()),epoch=useRef(0),paused=useRef(true),saving=useRef(false),audio=useRef(null),mounted=useRef(true),segmentBase=useRef(1),drafts=useRef(new DraftClient(api)),draftOwner=useRef(null),startGuard=useRef(false),preflight=useRef(new DeviceCheck()),deviceTimer=useRef(null),played=useRef(new Map()),focusLoss=useRef(0);
 useEffect(()=>{mounted.current=true;(async()=>{try{const u=await api('/me');if(!mounted.current)return;setUser(u);if(!u||u.admin)return;const aid=new URLSearchParams(location.search).get('application');if(!aid){setError('Open an interview from My Applications.');return;}const f=await api('/v2/applications/'+encodeURIComponent(aid));if(!mounted.current)return;current.current=f;setFlow(f);await restore(f);await allowance(f);setStatus(f.status==='completed'?'answers-completed':'ready');}catch(e){if(mounted.current)setError(e.message);}})();
 const unload=e=>{if(voice.current?.state==='live'){e.preventDefault();e.returnValue='Interview audio is active.';}};
 window.addEventListener('beforeunload',unload);
 return()=>{mounted.current=false;paused.current=true;epoch.current++;clearInterval(deviceTimer.current);preflight.current.close();closeSpeech();stopAudio();voice.current?.stop();drafts.current.invalidate();window.removeEventListener('beforeunload',unload);};},[]);
 useEffect(()=>{const f=current.current;if(!f?.active||draftOwner.current!==f.active.id||saving.current||text.length>6000)return;let cancelled=false;const t=setTimeout(async()=>{if(draftOwner.current!==f.active.id||saving.current)return;setDraftStatus('Saving draft…');try{const r=await drafts.current.save(f.application_id,f.active.id,text);if(!cancelled&&r)setDraftStatus('Draft saved; not yet submitted.');}catch(e){if(!cancelled){setDraftStatus('Draft not saved. Keep this tab open.');stopWithError(e.message);}}},1000);return()=>{cancelled=true;clearTimeout(t);};},[text,flow?.active?.id]);
 useEffect(()=>{const count=()=>{if(started&&flow&&flow.status!=='completed'&&status!=='technical-stop'){focusLoss.current++;setFocusNote('Leaving or switching away from this window is recorded and shared with the hiring team.');}};
  const onVisibility=()=>{if(document.hidden)count();};
  document.addEventListener('visibilitychange',onVisibility);window.addEventListener('blur',count);
  return()=>{document.removeEventListener('visibilitychange',onVisibility);window.removeEventListener('blur',count);};},[started,flow,status]);
 function paint(){if(mounted.current)setText(ctl.current.transcript());}
 function stopAudio(){const a=audio.current;audio.current=null;if(a){a.stopReveal?.();a.player.onended=null;a.player.onerror=null;a.player.pause();a.disconnect();URL.revokeObjectURL(a.url);a.resolve(false);}}
 function closeSpeech(){const s=speech.current;speech.current=null;if(!s)return closing.current;s.processor.port.onmessage=null;s.processor.disconnect();s.input.disconnect();s.silent.disconnect();s.socket.onmessage=null;s.socket.onerror=null;s.socket.onclose=null;s.cancel?.();closing.current=new Promise(resolve=>{if(s.socket.readyState===3)return resolve();const t=setTimeout(resolve,5500);s.socket.onclose=()=>{clearTimeout(t);resolve();};s.socket.close();});return closing.current;}
 function stopWithError(message){paused.current=true;epoch.current++;ctl.current.pause();stopAudio();voice.current?.stop();closeSpeech();if(mounted.current){setStatus('technical-stop');setError(message);}}
 // A dropped voice socket is recoverable: keep the transcript, let the
 // candidate reconnect with Tap to speak or submit what they have.
 function voiceLost(why){if(paused.current)return;closeSpeech();const has=ctl.current.transcript().trim().length>0;if(mounted.current){setWarn((why||'Voice connection dropped.')+(has?' Your words so far are kept below.':' Tap to speak again to reconnect.'));setStatus(has?'voice-lost':'awaiting-tap');}}
 async function allowance(f=current.current){if(!f?.active){return null;}return api('/v2/applications/'+f.application_id+'/playback');}
 async function safeAllowance(f=current.current){try{return await allowance(f);}catch{return null;}}
 async function restore(f){draftOwner.current=null;drafts.current.invalidate();if(mounted.current)setDisclosure({qid:f.active?.id,count:played.current.get(f.active?.id)||0});ctl.current.begin();ctl.current.pause();if(f.active){const d=await drafts.current.load(f.application_id,f.active.id);if(d?.transcript)ctl.current.segments.set(0,d.transcript);draftOwner.current=f.active.id;if(mounted.current){setText(d?.transcript||'');setDraftStatus(d?.transcript?'Saved draft restored.':'');}}else if(mounted.current)setText('');}
 async function checkDevices(){setBusy(true);setError('');setDevicesReady(false);setMicDetected(false);clearInterval(deviceTimer.current);try{const stream=await preflight.current.open();if(!mounted.current)return;setDevicesReady(true);deviceTimer.current=setInterval(()=>{if(preflight.current.level()>.015)setMicDetected(true);},100);stream.getTracks().forEach(t=>t.onended=()=>{setDevicesReady(false);setError('The microphone disconnected. Run device checks again.');});}catch(e){if(mounted.current)setError(e.message);}finally{if(mounted.current)setBusy(false);}}
 function retryable(e){e.retryable=true;return e;}
 async function connectSpeech(){for(let attempt=0;;attempt++){try{return await openSpeech();}catch(e){if(!e.retryable||attempt>=2||paused.current)throw e;await closeSpeech();await new Promise(r=>setTimeout(r,400*(attempt+1)));if(paused.current)throw Error('Listening cancelled.');}}}
 async function openSpeech(){
  await closeSpeech();const media=voice.current,run=epoch.current;if(paused.current||media?.state!=='live')throw Error('Interview stopped before listening started.');
  const base=segmentBase.current;segmentBase.current+=10001;await media.prepareSpeechWorklet();if(paused.current||run!==epoch.current)throw Error('Listening cancelled.');
  const processor=new AudioWorkletNode(media.context,'interview-pcm'),input=media.context.createMediaStreamSource(new MediaStream(media.stream.getAudioTracks())),silent=media.context.createGain();silent.gain.value=0;input.connect(processor);processor.connect(silent);silent.connect(media.context.destination);
  const socket=new WebSocket((location.protocol==='https:'?'wss:':'ws:')+'//'+location.host+'/api/v2/voice/'+current.current.application_id);const state={socket,processor,input,silent};speech.current=state;
  processor.port.onmessage=e=>{if(!paused.current&&run===epoch.current&&socket.readyState===1){if(socket.bufferedAmount>64000){stopWithError('Voice network is behind. Capture has been stopped for technical review.');return;}socket.send(e.data);}};
  let live=false;
  await new Promise((resolve,reject)=>{const t=setTimeout(()=>reject(retryable(Error('Voice connection timed out.'))),20000);state.cancel=()=>{clearTimeout(t);reject(Error('Listening cancelled.'));};
   socket.onmessage=e=>{if(run!==epoch.current)return;let msg;try{msg=JSON.parse(e.data);}catch{return;}if(msg.event==='ready'){clearTimeout(t);state.cancel=null;live=true;resolve();return;}if(msg.event==='error'){clearTimeout(t);if(msg.code==='usage_limit_reached'){if(!live)reject(Error(msg.message));stopWithError(msg.message);}else{if(!live)reject(retryable(Error(msg.message)));voiceLost(msg.message);}return;}if(paused.current)return;const index=base+msg.utterance_idx;
    if(msg.event==='vad.speech_start')ctl.current.speechStart(index);
    if(msg.event==='vad.speech_end')ctl.current.speechEnd();
    if(msg.event==='transcript.partial')ctl.current.partial(index);
    if(msg.event==='transcript.final')ctl.current.final(index,msg.text);
    if(ctl.current.transcript().length>6000){stopWithError('Answer exceeds the supported size. No text was silently truncated. Contact support.');return;}paint();
   };
   socket.onerror=()=>{clearTimeout(t);if(!live){reject(retryable(Error('Voice connection failed.')));return;}voiceLost('Voice connection failed.');};
   socket.onclose=()=>{clearTimeout(t);if(!live){reject(retryable(Error('Voice connection failed.')));return;}voiceLost('Voice connection lost.');};
  });
  if(paused.current||run!==epoch.current)throw Error('Listening cancelled.');
 }
 function trackReveal(player,text,qid){
  const total=wordsOf(text).length;if(!total)return null;let frame=0,last=-1;
  const step=()=>{const shown=revealedAt(player.currentTime,player.duration,total);if(shown!==last){last=shown;played.current.set(qid,shown);if(mounted.current)setDisclosure({qid,count:shown});}frame=requestAnimationFrame(step);};
  frame=requestAnimationFrame(step);return()=>cancelAnimationFrame(frame);
 }
 async function speak(introduction=false){
  const f=current.current,run=epoch.current;setStatus('processing');let blob;
  if(!introduction)setDisclosure({qid:f.active.id,count:0});
  try{blob=await api('/v2/applications/'+f.application_id+(introduction?'/intro':'/speech'),introduction?{}:{question_id:f.active.id},true);}
  catch(e){
   if(paused.current||run!==epoch.current)return false;
   // TTS outage is recoverable: reveal the question text and let the candidate answer.
   if(introduction){setError('Introduction audio is unavailable. Continue with the first question below.');return true;}
   revealFull();setWarn('Question audio is unavailable right now. Read the question above, then tap to speak.');setStatus('awaiting-tap');return true;
  }
  finally{if(!introduction){try{await allowance();}catch{}}}
  if(paused.current||run!==epoch.current)return false;
  return new Promise(resolve=>{const url=URL.createObjectURL(blob),player=new Audio(url);let disconnect;
   try{disconnect=voice.current.routeQuestion(player);}catch(e){URL.revokeObjectURL(url);revealFull();setWarn('Interview audio routing failed. Read the question above, then tap to speak.');setStatus('awaiting-tap');resolve(true);return;}
   const stopReveal=introduction?null:trackReveal(player,f.active?.text,f.active?.id);audio.current={player,url,disconnect,resolve,stopReveal};setStatus('ai-speaking');
   player.onended=()=>{stopReveal?.();disconnect();URL.revokeObjectURL(url);audio.current=null;if(run===epoch.current&&!introduction){const count=wordsOf(f.active.text).length;played.current.set(f.active.id,count);setDisclosure({qid:f.active.id,count});setStatus('awaiting-tap');}paint();resolve(true);};
   player.onerror=()=>{stopAudio();if(run===epoch.current&&!paused.current&&!introduction){revealFull();setWarn('Question playback failed. Read the question above, then tap to speak.');setStatus('awaiting-tap');}resolve(true);};
   player.play().catch(()=>{stopAudio();if(run===epoch.current&&!paused.current&&!introduction){revealFull();setWarn('Browser blocked audio playback. Read the question above, then tap to speak.');setStatus('awaiting-tap');}resolve(true);});
  });
 }
 function revealFull(){const q=current.current?.active;if(!q)return;const total=wordsOf(q.text).length;played.current.set(q.id,total);setDisclosure({qid:q.id,count:total});}
 function voiceFactory(){return new InterviewVoice({api,onChange:v=>{if(mounted.current)setVoiceState(v.state);},onFailure:stopWithError});}
 async function begin(){
  if(startGuard.current||saving.current||started||!consent||!devicesReady||!micDetected)return;
  startGuard.current=true;setStarted(true);setBusy(true);setError('');setWarn('');const run=++epoch.current;paused.current=false;
  try{
   clearInterval(deviceTimer.current);await preflight.current.close();
   const f=await api('/v2/applications/'+current.current.application_id);if(epoch.current!==run||paused.current)throw Error('Start cancelled.');
   current.current=f;setFlow(f);if(f.status==='completed'){paused.current=true;setStatus('answers-completed');return;}if(!f.active)throw Error('Next question is not ready. Contact support.');
   await drafts.current.chain;await restore(f);const prior=ctl.current.transcript();ctl.current.begin();if(prior)ctl.current.segments.set(0,prior);paused.current=false;
   voice.current=voiceFactory();await voice.current.begin();
   if(epoch.current!==run||paused.current){voice.current.stop();throw Error('Start cancelled.');}
   const p=await safeAllowance(f);
   if(!f.answers.length&&!prior){const ok=await speak(true);if(!ok)return;}
   if(!prior&&(p===null||p.deliveries_remaining>0)){await speak();return;}
   revealFull();setStatus('awaiting-tap');
  }catch(e){stopWithError(e.message);}finally{startGuard.current=false;if(mounted.current)setBusy(false);}
 }
 async function tapToSpeak(){
  if(busy||saving.current||(status!=='awaiting-tap'&&status!=='voice-lost'))return;
  setError('');setWarn('');setStatus('processing');const run=epoch.current;
  try{await connectSpeech();if(paused.current||run!==epoch.current)return;setStatus('listening');}
  catch(e){stopWithError(e.message);}
 }
 async function doneSpeaking(){
  if(busy||saving.current||(status!=='listening'&&status!=='voice-lost'))return;
  let answer=ctl.current.transcript().trim();
  if(!answer){
   // First-question race: the coldest upstream STT connection can emit the
   // final transcript event a moment AFTER the candidate stops speaking and
   // taps done. Wait briefly for that late final before declaring the answer
   // empty; the mic socket is still open and events keep arriving.
   const live=!!speech.current;
   if(live){setError('');setStatus('processing');
    const deadline=performance.now()+2500;
    while(performance.now()<deadline){answer=ctl.current.transcript().trim();if(answer)break;await new Promise(r=>setTimeout(r,150));}
   }
   if(!answer){setError(live?'Still transcribing your last words. Tap “I’m done speaking” again in a moment, or keep speaking.':'No speech was captured yet. Answer out loud, then tap “I’m done speaking”.');setStatus(live?'listening':'awaiting-tap');return;}
  }
  setStatus('processing');setBusy(true);
  try{await closeSpeech();}catch{}
  if(mounted.current)setBusy(false);
  submit(answer);
 }
 async function submit(answer){
  if(saving.current)return;
  if(!answer.trim()){setStatus('awaiting-tap');return;}
  if(answer.length>6000){stopWithError('Answer exceeds the supported size. No text was silently truncated. Contact support.');return;}
  const f=current.current,run=epoch.current,event=crypto.randomUUID();saving.current=true;setBusy(true);setStatus('saving');
  try{
   await drafts.current.chain;
   const next=await api('/v2/applications/'+f.application_id+'/answer',{event_id:event,version:f.version,question_id:f.active.id,answer,focus_losses:focusLoss.current});
   current.current=next;setFlow(next);drafts.current.invalidate();draftOwner.current=null;
   if(paused.current||run!==epoch.current){await restore(next);setStatus(next.status==='completed'?'answers-completed':'technical-stop');return;}
   await advance(next);
  }catch(e){stopWithError(e.message+' Contact support before retrying an uncertain submission.');}finally{saving.current=false;if(mounted.current)setBusy(false);}
 }
 async function advance(next){
  current.current=next;setFlow(next);setText('');setWarn('');focusLoss.current=0;setFocusNote('');
  if(next.status==='completed'){paused.current=true;epoch.current++;stopAudio();await voice.current?.stop();ctl.current.complete();setStatus('completed');return;}
  if(paused.current){setStatus('technical-stop');await allowance(next);return;}
  await restore(next);ctl.current.begin();const p=await safeAllowance(next);
  if(p===null||p.deliveries_remaining>0){await speak();return;}
  revealFull();setStatus('awaiting-tap');
 }
 async function leave(){if(busy)return;if(!confirm('Exit this interview? Submitted answers stay saved; an unfinished answer is not a submitted answer.'))return;setBusy(true);paused.current=true;epoch.current++;ctl.current.pause();stopAudio();await closeSpeech();clearInterval(deviceTimer.current);try{await preflight.current.close();await drafts.current.chain;await voice.current?.stop();location.assign('/candidate/workspace/applications');}catch(e){setError('Could not finish saving: '+e.message);setStatus('technical-stop');}finally{setBusy(false);}}
 const aiSpeaking=status==='ai-speaking',listening=status==='listening',done=flow?.status==='completed';
 const label={'ready':'Ready when you are','ai-speaking':'Interviewer is speaking…','awaiting-tap':'Your turn — tap to speak','listening':'Listening… tap “I’m done speaking” when finished','voice-lost':'Voice dropped — your words are kept; reconnect or finish below','processing':'Processing your response…','saving':'Saving your response…','completed':'Interview submitted','answers-completed':'Answers submitted','technical-stop':'Technical interruption'}[status]||'Preparing interview…';
 const shown=disclosure.qid===flow?.active?.id?disclosure.count:0;
 return <main className="focused-room"><header><a href="/candidate/workspace/applications">teamrecrut · AI Interview</a><div><button onClick={()=>setHelp(!help)}>Help</button><button onClick={leave} disabled={busy}>Exit interview</button></div></header>
 {help&&<section className="room-help"><h2>Interview help</h2><p>After the interviewer finishes each question, tap “Tap to speak” and answer out loud, then tap “I’m done speaking”. Your speech is transcribed live and saved as you go. If audio drops, your words are kept — reconnect with Tap to speak or finish with the done button. Leaving or switching away from this window is recorded and shared with the hiring team. For a technical problem, use your in-app support inbox. No typing mode is available here.</p><p>This is a voice-only interview. Your speech is transcribed by Sarvam for this interview; drafts and submitted answers are saved, and submitted records are sent to ClickUp for authorised human review. No camera is used and no new video is recorded.</p><a href="/candidate/workspace/help" target="_blank" rel="noopener noreferrer">Open Help & Support</a></section>}
 {error&&<p role="alert" className="room-error">{error}</p>}
 {user===undefined?<p>Checking interview access…</p>:!user?<p><a href="/candidate/login">Sign in as a candidate</a>, then open My Interviews.</p>:user.admin?<p>Candidate access is required. <a href="/recruiter/workspace/dashboard">Return to recruiter dashboard</a></p>:!flow?<p><a href="/candidate/workspace/applications">Open an application to enter its interview.</a></p>:<>
 <h1>Your experience, in your words.</h1>
 {!started&&!done&&<section className="room-preflight"><h2>Before you begin</h2><p>This is a voice interview. The interviewer speaks each question aloud — it also appears on screen. When the question ends, tap “Tap to speak”, answer out loud, then tap “I’m done speaking”. No camera, no typing.</p><button onClick={checkDevices} disabled={busy}>Check your microphone</button><p role="status">{devicesReady?(micDetected?'Microphone connected · signal detected':'Microphone connected · speak to test'):'Device checks not completed'}</p>
 <label><input type="checkbox" checked={consent} onChange={e=>setConsent(e.target.checked)}/>I consent to voice processing for this interview.</label>
 <button onClick={begin} disabled={busy||!devicesReady||!micDetected||!consent}>Begin interview</button></section>}
 <div className="room-participants"><section className="room-interviewer"><h2>AI interviewer</h2><VoiceVisualizer tone="interviewer" active={aiSpeaking} getMeter={()=>voice.current?.meterFor('question')} label={aiSpeaking?'Speaking':''}/><p>{aiSpeaking?'Speaking':'Here to listen'}</p></section><section className="room-candidate"><h2>You</h2><VoiceVisualizer tone="candidate" active={listening} getMeter={()=>voice.current?.meterFor('voice')} label={listening?'Listening':''}/><p>{listening?'Your voice is being transcribed live':started?'Tap to speak when the question ends':'Waiting to begin'}</p></section></div>
 {!done&&<section className="room-question"><SpokenQuestion text={flow.active?.text} revealed={shown}/></section>}
 <p className="room-state" role="status">{label}</p>
 {warn&&<p className="room-warn" role="status">{warn}</p>}
 {focusNote&&<p className="room-warn" role="alert">{focusNote}</p>}
 {started&&!done&&(status==='awaiting-tap'||status==='voice-lost')&&<button className="room-tap" onClick={tapToSpeak} disabled={busy}>Tap to speak</button>}
 {started&&!done&&(status==='listening'||(status==='voice-lost'&&text.trim()))&&<button className="room-done" onClick={doneSpeaking} disabled={busy}>I’m done speaking</button>}
 {started&&!done&&status!=='technical-stop'&&<section className="room-transcript"><h2>Your response</h2><p>{text||'Your speech transcript appears here.'}</p><small>{draftStatus}</small></section>}
 {status==='technical-stop'&&<section className="room-help"><p>No answer has been silently resubmitted. Contact support; automatic retry after an uncertain submission requires a separately approved recovery flow.</p></section>}
 {done&&<p>Your saved answers are submitted for human review.</p>}
 </>}
 </main>;
}
