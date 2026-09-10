// Subject: one candidate interview, one inline self-view, one Begin gesture.
// Preserve Flashspace paper #faf9fd, ink #241c38, lilac #ece5ff, violet #7044dd.
// Layout: [current question + state | self-view]; no floating recording controls.
// Clear state hierarchy borrows the simplicity of a pocket device, not a dashboard.
import React,{useEffect,useRef,useState} from 'react';
import {TurnController} from './turn-controller.mjs';
import {InterviewCapture} from './interview-capture.mjs';
import '../RoleManager.css';
import './integrated-interview.css';

async function api(path,body,raw=false){
 const response=await fetch('/api'+path,{credentials:'same-origin',method:body?'POST':'GET',headers:{'X-Requested-With':'Flashspace',...(body?{'Content-Type':'application/json'}:{})},...(body?{body:JSON.stringify(body)}:{})});
 if(!response.ok){let data;try{data=await response.json();}catch{}throw Error(data?.error||'The request failed. Saved answers are retained.');}
 return raw?response.blob():response.json();
}

export default function IntegratedInterview(){
 const [user,setUser]=useState(undefined),[roles,setRoles]=useState([]),[apps,setApps]=useState([]),[flow,setFlow]=useState(null),[role,setRole]=useState(''),[experience,setExperience]=useState('');
 const [consent,setConsent]=useState(false),[status,setStatus]=useState('paused'),[error,setError]=useState(''),[text,setText]=useState(''),[captureState,setCaptureState]=useState('idle'),[busy,setBusy]=useState(false),[playback,setPlayback]=useState(null),[download,setDownload]=useState(null),[typing,setTyping]=useState(false);
 const current=useRef(null),capture=useRef(null),video=useRef(null),socketRef=useRef(null),node=useRef(null),ctl=useRef(new TurnController()),epoch=useRef(0),paused=useRef(true),checking=useRef(false),pendingSave=useRef(false),audio=useRef(null),timer=useRef(null),nextCheck=useRef(0),mounted=useRef(true),localURL=useRef(null),intro=useRef(false),segmentBase=useRef(0);
 useEffect(()=>{mounted.current=true;(async()=>{try{const u=await api('/me');if(!mounted.current)return;setUser(u);if(u){const [r,a]=await Promise.all([api('/v2/roles'),api('/applications')]);setRoles(r);setApps(a);const aid=new URLSearchParams(location.search).get('application');if(aid)await load(aid);}}catch(e){setError(e.message);}})();const unload=e=>{if(['recording','paused','uploading'].includes(capture.current?.state)){e.preventDefault();e.returnValue='Interview recording/upload is still active.';}};window.addEventListener('beforeunload',unload);return()=>{mounted.current=false;epoch.current++;clearInterval(timer.current);closeSpeech();stopAudio();capture.current?.stop();if(localURL.current)URL.revokeObjectURL(localURL.current);window.removeEventListener('beforeunload',unload);};},[]);
 function paint(){if(mounted.current){setStatus(ctl.current.state);setText(ctl.current.transcript());}}
 function stopAudio(){if(audio.current){const value=audio.current;audio.current=null;value.audio.pause();value.audio.onended=null;value.disconnect();URL.revokeObjectURL(value.url);value.resolve(false);}}
 async function closeSpeech(){const socket=socketRef.current;socketRef.current=null;node.current?.disconnect();if(node.current)node.current.port.onmessage=null;node.current=null;if(!socket)return;socket.onmessage=null;socket.onerror=null;socket.onclose=null;await new Promise(resolve=>{if(socket.readyState===3)return resolve();const t=setTimeout(resolve,5500);socket.onclose=()=>{clearTimeout(t);resolve();};socket.close();});}
 function pause(message=''){paused.current=true;epoch.current++;ctl.current.pause();stopAudio();capture.current?.pause();closeSpeech();clearInterval(timer.current);setStatus('paused');if(message)setError(message);}
 async function allowance(f=current.current){if(!f?.active){setPlayback(null);return null;}const value=await api('/v2/applications/'+f.application_id+'/playback');setPlayback(value);return value;}
 async function load(aid){if(capture.current&&['recording','paused','uploading'].includes(capture.current.state))return;setBusy(true);try{const f=await api('/v2/applications/'+aid);current.current=f;setFlow(f);await allowance(f);intro.current=f.answers.length>0;setStatus(f.status==='completed'?'completed':'paused');history.replaceState(null,'','/interview-v2?application='+aid);}catch(e){setError(e.message);}finally{setBusy(false);}}
 async function apply(e){e.preventDefault();setBusy(true);setError('');try{const f=await api('/v2/applications',{role_id:role,experience,consent:true,consent_version:'flashspace-sarvam-conversation-v2'});current.current=f;setFlow(f);await allowance(f);history.replaceState(null,'','/interview-v2?application='+f.application_id);}catch(e){setError(e.message);}finally{setBusy(false);}}
 async function connectSpeech(){
  await closeSpeech();const media=capture.current;if(!media||media.state!=='recording')throw Error('Interview recording must be active before listening.');
  const run=epoch.current;const base=segmentBase.current;segmentBase.current+=10001;
  await media.context.audioWorklet.addModule('/v2-pcm-worklet.js');
  const processor=new AudioWorkletNode(media.context,'interview-pcm');node.current=processor;
  // STT receives only the microphone, not the mixed interviewer playback track.
  const input=media.context.createMediaStreamSource(new MediaStream(media.stream.getAudioTracks()));const silent=media.context.createGain();silent.gain.value=0;input.connect(processor);processor.connect(silent);silent.connect(media.context.destination);
  const socket=new WebSocket((location.protocol==='https:'?'wss:':'ws:')+'//'+location.host+'/api/v2/voice/'+current.current.application_id);socketRef.current=socket;
  processor.port.onmessage=e=>{if(!paused.current&&run===epoch.current&&socket.readyState===1){if(socket.bufferedAmount>64000){pause('Network too slow. Interview and recording paused.');return;}socket.send(e.data);}};
  await new Promise((resolve,reject)=>{
   const timeout=setTimeout(()=>reject(Error('Voice connection timed out.')),20000);
   socket.onmessage=e=>{if(run!==epoch.current)return;let msg;try{msg=JSON.parse(e.data);}catch{return;}
    if(msg.event==='ready'){clearTimeout(timeout);resolve();return;}
    if(msg.event==='error'){clearTimeout(timeout);reject(Error(msg.message));pause(msg.message);return;}
    if(paused.current)return;const index=base+msg.utterance_idx;
    if(msg.event==='vad.speech_start'){ctl.current.speechStart(index);stopAudio();if(pendingSave.current){pause('Speech resumed while an answer was being committed. The recording is paused; reload the saved question before continuing.');return;}}
    if(msg.event==='vad.speech_end')ctl.current.speechEnd();
    if(msg.event==='transcript.partial'){ctl.current.partial(index);stopAudio();}
    if(msg.event==='transcript.final')ctl.current.final(index,msg.text);
    if(ctl.current.transcript().length>6000)pause('Answer is too long. Please review it using the typing alternative; nothing was submitted automatically.');paint();
   };
   socket.onerror=()=>{clearTimeout(timeout);reject(Error('Voice connection failed.'));};
   socket.onclose=()=>{input.disconnect();clearTimeout(timeout);reject(Error('Voice connection closed.'));if(!paused.current&&run===epoch.current)pause('Voice connection lost. Your submitted answers remain saved.');};
  });
 }
 async function speak(introduction=false){
  const f=current.current,token=ctl.current.epoch,run=epoch.current;setStatus('processing');
  let blob;try{blob=await api('/v2/applications/'+f.application_id+(introduction?'/intro':'/speech'),introduction?{}:{question_id:f.active.id},true);}finally{if(!introduction)await allowance();}
  if(paused.current||run!==epoch.current||!ctl.current.canPlay(token))return false;
  return new Promise(resolve=>{
   const url=URL.createObjectURL(blob),player=new Audio(url);const disconnect=capture.current.routeQuestion(player);audio.current={audio:player,url,disconnect,resolve};setStatus('ai-speaking');
   player.onended=()=>{disconnect();URL.revokeObjectURL(url);audio.current=null;if(!introduction&&run===epoch.current)ctl.current.playbackEnded(token);paint();resolve(true);};
   player.onerror=()=>{stopAudio();pause('Question playback failed. Resume listening or use an available replay.');};
   player.play().catch(()=>{stopAudio();pause('Browser playback was blocked. Resume from this interview screen.');});
  });
 }
 function checks(){clearInterval(timer.current);timer.current=setInterval(()=>{if(!paused.current&&!checking.current&&!pendingSave.current&&ctl.current.ready()&&Date.now()>=nextCheck.current)endCheck();},300);}
 async function begin(){
  if(!consent){setError('Accept recording consent before beginning.');return;}setBusy(true);setError('');
  try{
   const f=await api('/v2/applications/'+current.current.application_id);current.current=f;setFlow(f);if(f.status==='completed'){setStatus('completed');return;}
   if(!f.active)throw Error('The next question is not ready. Wait briefly and resume.');
   const sameQuestion=flow?.active?.id===f.active.id;const prior=sameQuestion?ctl.current.transcript():'';
   ctl.current.begin();if(prior)ctl.current.segments.set(0,prior);
   paused.current=false;epoch.current++;
   if(capture.current?.state==='paused')capture.current.resume();
   else {
    if(capture.current&&capture.current.state!=='idle')throw Error('This recording needs review before a new capture can begin.');
    capture.current=new InterviewCapture({api,upload:async(rid,index,chunk)=>{const r=await fetch('/api/recordings/'+rid+'/chunk/'+index,{method:'POST',credentials:'same-origin',headers:{'X-Requested-With':'Flashspace','Content-Type':'application/octet-stream'},body:chunk});if(!r.ok)throw Error('Upload failed');},onChange:value=>{if(!mounted.current)return;setCaptureState(value.state);if(value.blob){if(localURL.current)URL.revokeObjectURL(localURL.current);localURL.current=URL.createObjectURL(value.blob);setDownload(localURL.current);}},onFailure:message=>pause(message)});
    const stream=await capture.current.begin(f.application_id,true);if(video.current)video.current.srcObject=stream;
   }
   await connectSpeech();const limit=await allowance(f);
   if(!intro.current){const ok=await speak(true);if(!ok)return;intro.current=true;await closeSpeech();ctl.current.begin();await connectSpeech();}
   checks();if(limit.initial_available&&!prior)await speak();else{ctl.current.state='listening';paint();}
  }catch(e){pause(e.message);}finally{setBusy(false);}
 }
 async function endCheck(){
  checking.current=true;const token=ctl.current.prepare();if(token===null){checking.current=false;return;}setStatus('processing');const f=current.current;
  try{const result=await api('/v2/applications/'+f.application_id+'/end-check',{question_id:f.active.id,version:f.version,answer:ctl.current.transcript()});if(paused.current||!ctl.current.canPlay(token))return;if(!result.complete){ctl.current.state='end-pending';nextCheck.current=Date.now()+15000;paint();return;}await submit(ctl.current.transcript(),token);}
  catch(e){pause(e.message);}finally{checking.current=false;}
 }
 async function submit(answer,token=null){
  if(pendingSave.current||!answer.trim()||answer.length>6000)return;pendingSave.current=true;setBusy(true);setStatus('saving');const f=current.current,run=epoch.current;
  try{const next=await api('/v2/applications/'+f.application_id+'/answer',{event_id:crypto.randomUUID(),version:f.version,question_id:f.active.id,answer});pendingSave.current=false;current.current=next;setFlow(next);setText('');
   if(next.status==='completed'){paused.current=true;epoch.current++;stopAudio();await closeSpeech();clearInterval(timer.current);ctl.current.complete();setStatus('uploading');const saved=await capture.current?.stop();setStatus(saved?.complete?'completed':'recording-incomplete');return;}
   if(paused.current||run!==epoch.current||(token!==null&&!ctl.current.canPlay(token))){ctl.current.begin();ctl.current.pause();setStatus('paused');await allowance(next);return;}
   await closeSpeech();ctl.current.begin();await connectSpeech();await allowance(next);await speak();
  }catch(e){pause(e.message+' Reload saved state before retrying an uncertain submission.');}finally{pendingSave.current=false;setBusy(false);}
 }
 async function replay(){if(ctl.current.speaking||ctl.current.pending.size||busy||paused.current)return;setBusy(true);try{const p=await allowance();if(p.deliveries_remaining>0){ctl.current.epoch++;ctl.current.state='ai-speaking';await speak();}}catch(e){pause(e.message);}finally{setBusy(false);}}
 async function leave(){pause();setBusy(true);try{await capture.current?.stop();setCaptureState(capture.current?.state||'idle');setStatus('paused');}finally{setBusy(false);}}
 const label={'paused':'Ready / paused','ai-speaking':'Interviewer is speaking…','candidate-speaking':'Listening…','listening':'Your turn — speak now','end-pending':'Listening — take your time','processing':'Processing…','saving':'Saving your answer…','uploading':'Interview complete — finishing video upload…','completed':'Interview and recording saved','recording-incomplete':'Answers saved — recording needs attention'}[status]||status;
 return <main className="role-admin interview-integrated"><header><a href="/">← Careers / recruiter workspace</a><p className="role-kicker">AI INTERVIEW · INTEGRATED CAMERA PILOT</p></header>
 {error&&<p role="alert" className="role-error">{error}</p>}
 {user===undefined?<p>Loading interview access…</p>:!user?<p>Log in on the careers website, then return to your interview.</p>:!flow?<section className="role-editor"><h1>Your next conversation.</h1><p>Six shared questions, then four domain questions. Camera preview and recording belong to this interview—not a separate recorder.</p>
 <h2>Continue an interview</h2>{apps.map(a=><div key={a.id}>{a.role_title} · {a.status} {a.flow_version===2?<button onClick={()=>load(a.id)}>Resume interview</button>:<a href="/">Continue existing four-question application</a>}</div>)}
 <form onSubmit={apply}><h2>Apply and start a new interview</h2><label>Role<select required value={role} onChange={e=>setRole(e.target.value)}><option value="">Choose role</option>{roles.map(r=><option value={r.id} disabled={!r.bank} key={r.id}>{r.title}{!r.bank?' — domain bank required':''}</option>)}</select></label><label>Relevant experience<textarea required minLength={20} maxLength={4000} value={experience} onChange={e=>setExperience(e.target.value)}/></label><label className="interview-consent"><input required type="checkbox"/>I agree to Sarvam processing interview audio and saving answers for human review and ClickUp synchronization. I understand this is a fictional-data staging test.</label><button disabled={busy}>Create my interview</button></form></section>:<>
 <h1>{flow.active?.stage==='domain'?'Your role, in practice.':'Your experience, in your words.'}</h1><div className="interview-columns"><section className="role-editor"><p className="role-kicker">{flow.active?.stage||'Complete'} · {flow.answers.length} answers saved · 10 core questions + up to 4 clarifiers</p><h2 aria-live="polite">{label}</h2><h3>{flow.active?.text}</h3>
 {flow.status!=='completed'&&<><label className="interview-consent"><input type="checkbox" checked={consent} disabled={captureState==='recording'} onChange={e=>setConsent(e.target.checked)}/>I consent to recording my camera, microphone and the interviewer’s audio for authorized human review. Temporary server copies can be lost on redeploy; only fictional data is allowed.</label>
 <div className="role-actions"><button disabled={busy||!consent||!paused.current} onClick={begin}>{captureState==='paused'?'Resume interview':'Begin interview'}</button><button className="role-secondary" disabled={busy||paused.current||!playback||playback.deliveries_remaining<=0||ctl.current.speaking} onClick={replay}>Hear again ({playback?.replays_remaining??2} left)</button><button className="role-secondary" onClick={()=>pause()}>Pause interview</button><button className="role-secondary" disabled={busy||paused.current||ctl.current.speaking||ctl.current.pending.size>0} onClick={()=>submit(ctl.current.transcript(),ctl.current.epoch)}>I'm finished answering</button><button className="role-secondary" onClick={()=>{pause();setTyping(true);setText(ctl.current.transcript());}}>Use typing alternative</button></div>
 {typing?<form onSubmit={e=>{e.preventDefault();submit(text);}}><label>Your answer<textarea required maxLength={6000} value={text} onChange={e=>setText(e.target.value)}/></label><button disabled={busy||!capture.current}>Save typed answer</button><p>Recording is paused during typed input. Resume to continue the spoken interview.</p></form>:<><p>Finalized speech transcript — submitted only after your turn ends.</p><p>{text||'Your answer appears here as you speak.'}</p></>}
 </>}
 <details><summary>Saved questions and answers</summary>{flow.answers.map(a=><section key={a.event_id}><h3>{a.stage}: {a.question}</h3><p>{a.answer}</p></section>)}</details></section>
 <aside className="role-editor interview-selfview"><h2>Your camera</h2><video ref={video} autoPlay muted playsInline aria-label="Your live camera preview"/><p role="status">{captureState==='recording'?'● Recording this interview':captureState==='paused'?'Camera and microphone paused':captureState==='saved'?'Temporary recording uploaded':captureState}</p><p>The video stays with this application across all its questions. Headphones help prevent playback echo.</p><p className="role-error">Temporary storage: 10 recordings / 50 MB each. Download your test copy promptly. A server replacement can remove it.</p>{download&&<a download="interview-recording.webm" href={download}>Download captured video</a>}{flow.status!=='completed'&&capture.current&&<button className="role-secondary" disabled={busy} onClick={leave}>Save recording segment & leave interview</button>}</aside></div>
 </>}
 </main>;
}
