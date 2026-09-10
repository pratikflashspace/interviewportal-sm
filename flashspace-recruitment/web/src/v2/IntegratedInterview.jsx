// One interview room: paper/lilac, prominent honest state, inline self-view.
// No global recording dock. Candidate recording and TTS share a session lifecycle.
import React,{useEffect,useRef,useState} from 'react';
import {TurnController} from './turn-controller.mjs';
import {InterviewCapture} from './interview-capture.mjs';
import {DraftClient} from './draft-client.mjs';
import '../RoleManager.css';
import './integrated-interview.css';
async function api(path,body,raw=false){
 const controller=new AbortController(),timeout=setTimeout(()=>controller.abort(),65000);
 try{const r=await fetch('/api'+path,{credentials:'same-origin',signal:controller.signal,method:body?'POST':'GET',headers:{'X-Requested-With':'Flashspace',...(body?{'Content-Type':'application/json'}:{})},...(body?{body:JSON.stringify(body)}:{})});if(!r.ok){let e;try{e=await r.json();}catch{}throw Error(e?.error||'Request failed; reload saved state before retrying.');}return raw?await r.blob():await r.json();}finally{clearTimeout(timeout);}
}
export default function IntegratedInterview(){
 const [user,setUser]=useState(undefined),[roles,setRoles]=useState([]),[apps,setApps]=useState([]),[flow,setFlow]=useState(null),[role,setRole]=useState(new URLSearchParams(location.search).get('role')||''),[experience,setExperience]=useState(''),[banks,setBanks]=useState(null);
 const [consent,setConsent]=useState(false),[status,setStatus]=useState('paused'),[error,setError]=useState(''),[text,setText]=useState(''),[captureState,setCaptureState]=useState('idle'),[busy,setBusy]=useState(false),[playback,setPlayback]=useState(null),[downloads,setDownloads]=useState([]),[typing,setTyping]=useState(false),[draftStatus,setDraftStatus]=useState(''),[orphans,setOrphans]=useState([]);
 const current=useRef(null),capture=useRef(null),video=useRef(null),speech=useRef(null),closing=useRef(Promise.resolve()),ctl=useRef(new TurnController()),epoch=useRef(0),paused=useRef(true),checking=useRef(false),saving=useRef(false),audio=useRef(null),timer=useRef(null),nextCheck=useRef(0),mounted=useRef(true),intro=useRef(false),segmentBase=useRef(1),drafts=useRef(new DraftClient(api)),draftOwner=useRef(null),continuation=useRef(null),urls=useRef([]),startGuard=useRef(false);
 useEffect(()=>{mounted.current=true;(async()=>{try{const u=await api('/me');if(!mounted.current)return;setUser(u);if(u){const [r,a]=await Promise.all([api('/v2/roles'),api('/applications')]);if(!mounted.current)return;setRoles(r);setApps(a);if(u.admin)setBanks(await api('/admin/v2-banks'));const aid=new URLSearchParams(location.search).get('application');if(aid)await load(aid);}}catch(e){if(mounted.current)setError(e.message);}})();
 const unload=e=>{if(['permission','recording','paused','uploading'].includes(capture.current?.state)){e.preventDefault();e.returnValue='Recording or upload active.';}};window.addEventListener('beforeunload',unload);
 return()=>{mounted.current=false;paused.current=true;epoch.current++;clearInterval(timer.current);closeSpeech();stopAudio();capture.current?.stop();drafts.current.invalidate();urls.current.forEach(URL.revokeObjectURL);window.removeEventListener('beforeunload',unload);};},[]);
 useEffect(()=>{if(video.current)video.current.srcObject=capture.current?.stream||null;},[captureState,flow?.application_id]);
 useEffect(()=>{const f=current.current;if(!f?.active||draftOwner.current!==f.active.id||saving.current||continuation.current||text.length>6000)return;let cancelled=false;const t=setTimeout(async()=>{if(draftOwner.current!==f.active.id||saving.current)return;setDraftStatus('Saving draft…');try{const r=await drafts.current.save(f.application_id,f.active.id,text);if(!cancelled&&r)setDraftStatus('Draft saved; not yet submitted.');}catch(e){if(!cancelled){setDraftStatus('Draft not saved. Keep this tab open.');setError(e.message);}}},1000);return()=>{cancelled=true;clearTimeout(t);};},[text,flow?.active?.id]);
 function paint(){if(mounted.current){setStatus(ctl.current.state);setText(ctl.current.transcript());}}
 function stopAudio(){const a=audio.current;audio.current=null;if(a){a.player.onended=null;a.player.onerror=null;a.player.pause();a.disconnect();URL.revokeObjectURL(a.url);a.resolve(false);}}
 function closeSpeech(){const s=speech.current;speech.current=null;if(!s)return closing.current;s.processor.port.onmessage=null;s.processor.disconnect();s.input.disconnect();s.silent.disconnect();s.socket.onmessage=null;s.socket.onerror=null;s.socket.onclose=null;s.cancel?.();closing.current=new Promise(resolve=>{if(s.socket.readyState===3)return resolve();const t=setTimeout(resolve,5500);s.socket.onclose=()=>{clearTimeout(t);resolve();};s.socket.close();});return closing.current;}
 function pause(message=''){paused.current=true;epoch.current++;ctl.current.pause();stopAudio();capture.current?.pause();closeSpeech();clearInterval(timer.current);if(mounted.current){setStatus('paused');if(message)setError(message);}}
 async function allowance(f=current.current){if(!f?.active){setPlayback(null);return null;}const p=await api('/v2/applications/'+f.application_id+'/playback');if(mounted.current&&current.current?.active?.id===p.question_id)setPlayback(p);return p;}
 async function restore(f){draftOwner.current=null;drafts.current.invalidate();ctl.current.begin();ctl.current.pause();continuation.current=null;if(f.active){const d=await drafts.current.load(f.application_id,f.active.id);if(d?.transcript)ctl.current.segments.set(0,d.transcript);draftOwner.current=f.active.id;setText(d?.transcript||'');setDraftStatus(d?.transcript?'Saved draft restored.':'');}else setText('');}
 async function acceptFlow(f){current.current=f;setFlow(f);intro.current=f.answers.length>0;history.replaceState(null,'','/interview-v2?application='+encodeURIComponent(f.application_id));await restore(f);await allowance(f);const r=await api('/v2/applications/'+f.application_id+'/recordings');setOrphans(r.recordings.filter(x=>x.status==='uploading'));setStatus(f.status==='completed'?'answers-completed':'paused');}
 async function load(aid){if(startGuard.current||saving.current||['recording','uploading'].includes(capture.current?.state))return;setBusy(true);try{await acceptFlow(await api('/v2/applications/'+aid));}catch(e){setError(e.message);}finally{setBusy(false);}}
 async function apply(e){e.preventDefault();setBusy(true);try{await acceptFlow(await api('/v2/applications',{role_id:role,experience,consent:true,consent_version:'flashspace-sarvam-conversation-v2'}));}catch(e){setError(e.message);}finally{setBusy(false);}}
 async function connectSpeech(){
  await closeSpeech();const media=capture.current,run=epoch.current;if(paused.current||media?.state!=='recording')throw Error('Interview paused before listening started.');
  const base=segmentBase.current;segmentBase.current+=10001;await media.context.audioWorklet.addModule('/v2-pcm-worklet.js');if(paused.current||run!==epoch.current)throw Error('Listening cancelled.');
  const processor=new AudioWorkletNode(media.context,'interview-pcm'),input=media.context.createMediaStreamSource(new MediaStream(media.stream.getAudioTracks())),silent=media.context.createGain();silent.gain.value=0;input.connect(processor);processor.connect(silent);silent.connect(media.context.destination);
  const socket=new WebSocket((location.protocol==='https:'?'wss:':'ws:')+'//'+location.host+'/api/v2/voice/'+current.current.application_id);const state={socket,processor,input,silent};speech.current=state;
  processor.port.onmessage=e=>{if(!paused.current&&run===epoch.current&&socket.readyState===1){if(socket.bufferedAmount>64000){pause('Voice network is behind. Interview paused.');return;}socket.send(e.data);}};
  await new Promise((resolve,reject)=>{const t=setTimeout(()=>reject(Error('Voice connection timed out.')),20000);state.cancel=()=>{clearTimeout(t);reject(Error('Listening cancelled.'));};
   socket.onmessage=e=>{if(run!==epoch.current)return;let msg;try{msg=JSON.parse(e.data);}catch{return;}if(msg.event==='ready'){clearTimeout(t);state.cancel=null;resolve();return;}if(msg.event==='error'){clearTimeout(t);reject(Error(msg.message));pause(msg.message);return;}if(paused.current)return;const index=base+msg.utterance_idx;
    if(msg.event==='vad.speech_start'){ctl.current.speechStart(index);stopAudio();}
    if(msg.event==='vad.speech_end')ctl.current.speechEnd();
    if(msg.event==='transcript.partial'){ctl.current.partial(index);stopAudio();}
    if(msg.event==='transcript.final')ctl.current.final(index,msg.text);
    if(ctl.current.transcript().length>6000){pause('Answer exceeds 6000 characters. Review your draft; no text was silently truncated.');setTyping(true);}paint();
   };
   socket.onerror=()=>{clearTimeout(t);reject(Error('Voice connection failed.'));if(!paused.current)pause('Voice connection failed. Resume when ready.');};
   socket.onclose=()=>{clearTimeout(t);reject(Error('Voice disconnected.'));if(!paused.current&&run===epoch.current)pause('Voice connection lost. Recording and interview paused.');};
  });
  if(paused.current||run!==epoch.current)throw Error('Listening cancelled.');
 }
 async function speak(introduction=false){
  const f=current.current,token=ctl.current.epoch,run=epoch.current;setStatus('processing');let blob;
  try{blob=await api('/v2/applications/'+f.application_id+(introduction?'/intro':'/speech'),introduction?{}:{question_id:f.active.id},true);}finally{if(!introduction)await allowance();}
  if(paused.current||run!==epoch.current||!ctl.current.canPlay(token))return false;
  return new Promise(resolve=>{const url=URL.createObjectURL(blob),player=new Audio(url);let disconnect;try{disconnect=capture.current.routeQuestion(player);}catch(e){URL.revokeObjectURL(url);pause(e.message);resolve(false);return;}audio.current={player,url,disconnect,resolve};setStatus('ai-speaking');
   player.onended=()=>{disconnect();URL.revokeObjectURL(url);audio.current=null;if(run===epoch.current){if(!introduction)ctl.current.playbackEnded(token);paint();}resolve(true);};player.onerror=()=>{stopAudio();pause('Question playback failed. Replay allowance counts delivered audio; resume or use typing.');};player.play().catch(()=>{stopAudio();pause('Browser blocked playback. Resume with the interview controls.');});});
 }
 function checks(){clearInterval(timer.current);timer.current=setInterval(()=>{if(!paused.current&&!checking.current&&!saving.current&&ctl.current.ready()&&Date.now()>=nextCheck.current)endCheck();},300);}
 function captureFactory(){return new InterviewCapture({api,upload:async(rid,index,chunk)=>{const controller=new AbortController(),t=setTimeout(()=>controller.abort(),30000);try{const r=await fetch('/api/recordings/'+rid+'/chunk/'+index,{signal:controller.signal,method:'POST',credentials:'same-origin',headers:{'X-Requested-With':'Flashspace','Content-Type':'application/octet-stream'},body:chunk});if(!r.ok)throw Error('Recording upload failed.');}finally{clearTimeout(t);}},onChange:v=>{if(!mounted.current)return;setCaptureState(v.state);if(v.blob){const url=URL.createObjectURL(v.blob);urls.current.push(url);setDownloads(rows=>rows.some(r=>r.id===v.id)?rows:[...rows,{id:v.id,url,complete:v.state==='saved',extension:v.mime?.includes('mp4')?'mp4':'webm'}]);}},onFailure:message=>pause(message)});}
 async function begin(){
  if(startGuard.current||saving.current||!consent)return;startGuard.current=true;setBusy(true);setError('');const startEpoch=++epoch.current;paused.current=false;
  try{
   const f=await api('/v2/applications/'+current.current.application_id);if(epoch.current!==startEpoch||paused.current)throw Error('Start cancelled.');
   const same=draftOwner.current===f.active?.id;const prior=same?(typing?text:ctl.current.transcript()):'';current.current=f;setFlow(f);
   if(f.status==='completed'){pause();setStatus('answers-completed');return;}if(!f.active)throw Error('Next question still processing. Resume shortly.');
   await drafts.current.chain;if(!same)await restore(f);ctl.current.begin();if(prior)ctl.current.segments.set(0,prior);draftOwner.current=f.active.id;setTyping(false);paused.current=false;
   if(capture.current?.state==='paused')capture.current.resume();
   else {if(!capture.current||['saved','failed','cancelled'].includes(capture.current.state))capture.current=captureFactory();await capture.current.begin(f.application_id,true);}
   if(epoch.current!==startEpoch||paused.current){capture.current.pause();throw Error('Start cancelled.');}
   if(video.current)video.current.srcObject=capture.current.stream;await connectSpeech();const p=await allowance(f);
   if(!intro.current&&!prior){const ok=await speak(true);if(!ok){pause('Introduction paused. Resume to continue.');return;}intro.current=true;await closeSpeech();ctl.current.begin();await connectSpeech();}
   checks();if(p.initial_available&&!prior)await speak();else{ctl.current.state='listening';paint();}
  }catch(e){pause(e.message);}finally{startGuard.current=false;setBusy(false);}
 }
 async function endCheck(){
  checking.current=true;const token=ctl.current.prepare();if(token===null){checking.current=false;return;}setStatus('processing');const f=current.current;
  try{if(continuation.current){await commitContinuation(token);return;}const result=await api('/v2/applications/'+f.application_id+'/end-check',{question_id:f.active.id,version:f.version,answer:ctl.current.transcript()});if(paused.current||!ctl.current.canPlay(token))return;if(!result.complete){ctl.current.state='end-pending';nextCheck.current=Date.now()+15000;paint();return;}await submit(ctl.current.transcript(),token);}catch(e){pause(e.message);}finally{checking.current=false;}
 }
 async function advance(next){
  continuation.current=null;current.current=next;setFlow(next);await closeSpeech();await restore(next);setText('');
  if(next.status==='completed'){paused.current=true;epoch.current++;stopAudio();clearInterval(timer.current);setStatus('uploading');const saved=await capture.current?.stop();ctl.current.complete();setStatus(saved?.complete?'completed':'answers-completed');return;}
  if(paused.current){setStatus('paused');await allowance(next);return;}
  ctl.current.begin();draftOwner.current=next.active.id;await connectSpeech();await allowance(next);await speak();checks();
 }
 async function commitContinuation(token){
  const info=continuation.current,answer=ctl.current.transcript();if(!info||saving.current)return;saving.current=true;setBusy(true);
  try{const f=current.current;if(f.status==='completed')throw Error('The final answer already completed this interview. Your continued speech is in the recording; recruiter review is required.');const next=await api('/v2/applications/'+f.application_id+'/continuation',{event_id:info.event_id,version:f.version,answer});current.current=next;setFlow(next);if(paused.current||!ctl.current.canPlay(token)){info.version=next.version;return;}await advance(next);}finally{saving.current=false;setBusy(false);}
 }
 async function submit(answer,token=null){
  if(saving.current||!answer.trim()||answer.length>6000)return;if(continuation.current){await commitContinuation(token??ctl.current.epoch);return;}
  const f=current.current,run=epoch.current,event=crypto.randomUUID();saving.current=true;setBusy(true);setStatus('saving');
  try{
   await drafts.current.chain;
   if(token!==null&&(paused.current||!ctl.current.canPlay(token))){paint();return;}
   const next=await api('/v2/applications/'+f.application_id+'/answer',{event_id:event,version:f.version,question_id:f.active.id,answer});current.current=next;setFlow(next);drafts.current.invalidate();draftOwner.current=null;
   // Continue capturing speech; don't discard it or play the new question while
   // the candidate resumes during the commit. Append to the last answer only
   // while the next question has not been delivered, enforced by the server.
   if(token!==null&&(!ctl.current.canPlay(token)||ctl.current.transcript()!==answer)){
    continuation.current={event_id:event,version:next.version};setDraftStatus('Additional speech belongs to the previous answer; waiting for you to finish.');
    if(next.status==='completed'){pause('Speech resumed after the final answer committed. Keep the recording for reviewer reconciliation; no new question will play.');return;}
    if(!paused.current){ctl.current.state=ctl.current.speaking?'candidate-speaking':'end-pending';paint();checks();}return;
   }
   if(paused.current||run!==epoch.current){await restore(next);setStatus(next.status==='completed'?'answers-completed':'paused');if(next.status==='completed')await capture.current?.stop();return;}
   await advance(next);
  }catch(e){pause(e.message+' Reload authoritative state before retrying an uncertain submission.');}finally{saving.current=false;setBusy(false);}
 }
 async function replay(){if(ctl.current.speaking||ctl.current.pending.size||busy||paused.current||continuation.current)return;setBusy(true);try{const p=await allowance();if(p.deliveries_remaining>0){ctl.current.epoch++;ctl.current.state='ai-speaking';await speak();}}catch(e){pause(e.message);}finally{setBusy(false);}}
 async function leave(){pause();setBusy(true);try{await drafts.current.chain;await capture.current?.stop();setStatus('paused');}finally{setBusy(false);}}
 async function recover(rid){if(!confirm('Mark this old unfinished recording incomplete? Do this only after its other browser tab has stopped recording. Uploaded parts remain for review.'))return;try{await api('/recordings/'+rid+'/abort',{});const r=await api('/v2/applications/'+current.current.application_id+'/recordings');setOrphans(r.recordings.filter(x=>x.status==='uploading'));}catch(e){setError(e.message);}}
 async function mapBank(role_id,bank){setBusy(true);try{await api('/admin/v2-banks',{role_id,bank});setBanks(await api('/admin/v2-banks'));setRoles(await api('/v2/roles'));}catch(e){setError(e.message);}finally{setBusy(false);}}
 const label={'paused':'Ready / paused','ai-speaking':'Interviewer is speaking…','candidate-speaking':'Listening…','listening':'Your turn — speak now','end-pending':'Listening — take your time','processing':'Processing…','saving':'Saving your answer…','uploading':'Interview complete — finishing video upload…','completed':'Interview and recording saved','answers-completed':'Answers submitted — check recording status'}[status]||status;
 return <main className="role-admin interview-integrated"><header><a href="/">← Careers / recruiter workspace</a><p className="role-kicker">AI INTERVIEW · INTEGRATED CAMERA PILOT</p></header>{error&&<p role="alert" className="role-error">{error}</p>}
 {user===undefined?<p>Loading interview access…</p>:!user?<p>Log in on the careers website, then return to your interview.</p>:!flow?<section className="role-editor"><h1>Your next conversation.</h1><p>Six shared questions, then four domain questions. Your recording stays with this interview.</p><h2>Continue an interview</h2>{apps.map(a=><div key={a.id}>{a.role_title} · {a.status} {a.flow_version===2?<button onClick={()=>load(a.id)}>Resume interview</button>:<a href="/">Continue existing four-question application</a>}</div>)}
 <form onSubmit={apply}><h2>Apply and start a new interview</h2><label>Role<select required value={role} onChange={e=>setRole(e.target.value)}><option value="">Choose role</option>{roles.map(r=><option value={r.id} disabled={!r.bank} key={r.id}>{r.title}{!r.bank?' — domain bank required':''}</option>)}</select></label><label>Relevant experience<textarea required minLength={20} maxLength={4000} value={experience} onChange={e=>setExperience(e.target.value)}/></label><label className="interview-consent"><input required type="checkbox"/>I agree to Sarvam processing interview audio, finalized draft storage, saved answers for human review and ClickUp synchronization. Fictional staging test only.</label><button disabled={busy||!roles.find(r=>r.id===role)?.bank}>Create my interview</button></form>
 {banks&&<section><h2>Recruiter: domain question-bank mappings</h2><p>Choose deliberately for new roles. Existing interviews retain their selected bank.</p>{banks.roles.map(r=><label key={r.id}>{r.title}<select disabled={busy} value={r.bank||''} onChange={e=>mapBank(r.id,e.target.value)}><option value="" disabled>Choose approved bank</option>{banks.banks.map(b=><option key={b}>{b}</option>)}</select></label>)}</section>}</section>:<>
 <h1>{flow.active?.stage==='domain'?'Your role, in practice.':'Your experience, in your words.'}</h1><div className="interview-columns"><section className="role-editor"><p className="role-kicker">{flow.active?.stage||'Complete'} · {flow.answers.length} answers saved · 10 core questions + up to 4 clarifiers</p><h2 aria-live="polite">{label}</h2><h3>{flow.active?.text}</h3>
 {flow.status!=='completed'&&<><label className="interview-consent"><input type="checkbox" checked={consent} disabled={['permission','recording','paused','uploading'].includes(captureState)} onChange={e=>setConsent(e.target.checked)}/>I consent to recording my camera, microphone and the interviewer’s audio for authorized human review. Temporary copies may be lost on redeploy. Fictional data only.</label>
 {orphans.map(r=><p key={r.id}>An earlier capture is unfinished. <button disabled={busy} onClick={()=>recover(r.id)}>Release old recording session</button></p>)}
 <div className="role-actions"><button disabled={busy||!consent||!paused.current||orphans.length>0} onClick={begin}>{captureState==='paused'?'Resume interview':'Begin interview'}</button><button className="role-secondary" disabled={busy||paused.current||!playback||playback.deliveries_remaining<=0||ctl.current.speaking||!!continuation.current} onClick={replay}>Hear again ({playback?.replays_remaining??2} left)</button><button className="role-secondary" onClick={()=>pause()}>Pause interview</button><button className="role-secondary" disabled={busy||paused.current||ctl.current.speaking||ctl.current.pending.size>0} onClick={()=>submit(ctl.current.transcript(),ctl.current.epoch)}>I'm finished answering</button><button className="role-secondary" disabled={busy} onClick={()=>{pause();setTyping(true);setText(ctl.current.transcript());}}>Use typing alternative</button><button className="role-secondary" disabled={busy||!paused.current} onClick={()=>load(flow.application_id)}>Reload saved state</button></div>
 {typing?<form onSubmit={e=>{e.preventDefault();submit(text);}}><label>Your answer<textarea required maxLength={6000} value={text} onChange={e=>{setText(e.target.value);ctl.current.segments=new Map(e.target.value?[[0,e.target.value]]:[]);}}/></label><button disabled={busy}>Save typed answer</button><p>Camera/microphone remain paused during typing. No recording is claimed for that part.</p></form>:<><p>Finalized speech transcript — submitted only after your turn ends.</p><p>{text||'Your answer appears here as you speak.'}</p></>}
 <p role="status">{draftStatus}</p></>}
 <details><summary>Saved questions and answers</summary>{flow.answers.map(a=><section key={a.event_id}><h3>{a.stage}: {a.question}</h3><p>{a.answer}</p></section>)}</details></section>
 <aside className="role-editor interview-selfview"><h2>Your camera</h2><video ref={video} autoPlay muted playsInline aria-label="Your live camera preview"/><p role="status">{captureState==='recording'?'● Recording this interview':captureState==='paused'?'Camera and microphone paused':captureState==='saved'?'Temporary recording segment uploaded':captureState}</p><p>The same recording continues across questions. Headphones reduce echo.</p><p className="role-error">Temporary storage: 10 recordings / 50 MB each. Download promptly; server replacement can remove videos. Partial segments are not a complete interview.</p>{downloads.map(d=><a key={d.id} download={'interview-'+d.id+'.'+d.extension} href={d.url}>Download captured {d.complete?'uploaded':'incomplete'} segment</a>)}{capture.current&&<button className="role-secondary" disabled={busy||captureState==='uploading'} onClick={leave}>Finish current recording segment</button>}</aside></div></>}
 </main>;
}
