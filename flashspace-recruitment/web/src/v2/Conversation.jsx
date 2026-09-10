// Flashspace v2: paper/lilac, honest prominent live state; no per-answer record button.
import React,{useEffect,useRef,useState} from 'react';
import {TurnController} from './turn-controller.mjs';
import '../RoleManager.css';
async function api(path,body,raw=false){
 const r=await fetch('/api'+path,{method:body?'POST':'GET',credentials:'same-origin',headers:{'X-Requested-With':'Flashspace',...(body?{'Content-Type':'application/json'}:{})},...(body?{body:JSON.stringify(body)}:{})});
 if(!r.ok){let e;try{e=await r.json();}catch{}throw new Error(e?.error||'Request failed. Saved answers are retained.');}
 return raw?r.blob():r.json();
}
const consent='flashspace-sarvam-conversation-v2';
export default function Conversation(){
 const [me,setMe]=useState(null),[roles,setRoles]=useState([]),[apps,setApps]=useState([]),[flow,setFlow]=useState(null);
 const [status,setStatus]=useState('paused'),[error,setError]=useState(''),[draft,setDraft]=useState(''),[busy,setBusy]=useState(false),[typing,setTyping]=useState(false),[bankData,setBankData]=useState(null),[reports,setReports]=useState([]),[allowance,setAllowance]=useState(null);
 const live=useRef(null),media=useRef(null),sound=useRef(null),ctl=useRef(new TurnController()),generation=useRef(0),checking=useRef(false),request=useRef(null),paused=useRef(true),timer=useRef(null),retryAfter=useRef(0),introDone=useRef(false),closing=useRef(Promise.resolve()),offset=useRef(0),preserved=useRef(null);
 useEffect(()=>{(async()=>{try{const u=await api('/me');setMe(u);if(u){setRoles(await api('/v2/roles'));setApps(await api('/applications'));if(u.admin){setBankData(await api('/admin/v2-banks'));setReports(await api('/admin/applications'));}}}catch(e){setError(e.message);}})();return()=>{halt();};},[]);
 function paint(){setStatus(ctl.current.state);setDraft(ctl.current.transcript());}
 function stopAudio(){if(sound.current){const s=sound.current;sound.current=null;s.audio.onended=null;s.audio.onerror=null;s.audio.pause();URL.revokeObjectURL(s.url);s.resolve(false);}}
 function closeMedia(){
  const m=media.current;media.current=null;if(!m)return closing.current;
  m.socket.onmessage=null;m.socket.onerror=null;m.socket.onclose=null;m.node.port.onmessage=null;
  m.stream.getTracks().forEach(t=>t.stop());m.node.disconnect();m.context.close();
  closing.current=new Promise(resolve=>{if(m.socket.readyState===3){resolve();return;}const limit=setTimeout(resolve,5500);m.socket.onclose=()=>{clearTimeout(limit);resolve();};m.socket.close();});
  return closing.current;
 }
 function keepDraft(){const f=live.current;if(f?.active&&ctl.current.segments.size)preserved.current={application:f.application_id,question:f.active.id,segments:[...ctl.current.segments.entries()]};}
 function halt(){keepDraft();paused.current=true;generation.current++;ctl.current.pause();stopAudio();closeMedia();clearInterval(timer.current);setStatus('paused');}
 async function playbackState(f=live.current){if(!f?.active){setAllowance(null);return null;}const s=await api('/v2/applications/'+f.application_id+'/playback');if(live.current?.active?.id===s.question_id)setAllowance(s);return s;}
 async function load(aid){halt();setError('');try{const f=await api('/v2/applications/'+aid);live.current=f;setFlow(f);setDraft('');introDone.current=f.answers.length>0;await playbackState(f);}catch(e){setError(e.message);}}
 async function create(e){e.preventDefault();setBusy(true);setError('');try{const body=Object.fromEntries(new FormData(e.currentTarget));const f=await api('/v2/applications',{...body,consent:true,consent_version:consent});live.current=f;setFlow(f);introDone.current=f.answers.length>0;preserved.current=null;await playbackState(f);setApps(await api('/applications'));}catch(e){setError(e.message);}finally{setBusy(false);}}
 async function openMic(){
  await closing.current;const gen=generation.current;
  offset.current=Math.max(-1,...ctl.current.segments.keys())+1;const segmentOffset=offset.current;
  const stream=await navigator.mediaDevices.getUserMedia({audio:{echoCancellation:true,noiseSuppression:true,channelCount:1}});
  if(paused.current||gen!==generation.current){stream.getTracks().forEach(t=>t.stop());throw new Error('Listening cancelled.');}
  let context,socket,node;
  try{
   context=new AudioContext({sampleRate:16000});
   if(context.sampleRate!==16000)throw new Error('This browser cannot capture 16 kHz audio. Use typing for this test.');
   await context.resume();await context.audioWorklet.addModule('/v2-pcm-worklet.js');
   socket=new WebSocket((location.protocol==='https:'?'wss:':'ws:')+'//'+location.host+'/api/v2/voice/'+live.current.application_id);
   node=new AudioWorkletNode(context,'interview-pcm');const source=context.createMediaStreamSource(stream);const mute=context.createGain();mute.gain.value=0;source.connect(node);node.connect(mute);mute.connect(context.destination);
   media.current={stream,context,socket,node};
   node.port.onmessage=e=>{if(!paused.current&&gen===generation.current&&socket.readyState===1){if(socket.bufferedAmount>64000){halt();setError('Network is too slow. Listening paused; finalized draft text is preserved in this tab.');}else socket.send(e.data);}};
   await new Promise((resolve,reject)=>{const timeout=setTimeout(()=>reject(new Error('Voice connection timed out.')),20000);
    socket.onmessage=e=>{let msg;try{msg=JSON.parse(e.data);}catch{return;}
     if(msg.event==='ready'){clearTimeout(timeout);resolve();return;}
     if(msg.event==='error'){clearTimeout(timeout);reject(new Error(msg.message));halt();setError(msg.message);return;}
     if(paused.current||gen!==generation.current)return;
     const index=segmentOffset+msg.utterance_idx;
     if(msg.event==='vad.speech_start'){
      ctl.current.speechStart(index);stopAudio();
      if(request.current){halt();setError('Speech resumed while an answer was saving. Any finalized draft is preserved in this tab. Reload saved state before continuing; no next question will play.');return;}
     }
     if(msg.event==='vad.speech_end')ctl.current.speechEnd();
     if(msg.event==='transcript.partial'){ctl.current.partial(index);if(sound.current)stopAudio();}
     if(msg.event==='transcript.final')ctl.current.final(index,msg.text);
     if(ctl.current.transcript().length>6000){halt();setTyping(true);setError('Answer exceeds 6000 characters. Review and shorten the retained text before submitting; nothing was silently truncated.');}
     paint();
    };
    socket.onerror=()=>{clearTimeout(timeout);reject(new Error('Voice connection failed.'));};
    socket.onclose=()=>{clearTimeout(timeout);reject(new Error('Voice connection closed.'));if(!paused.current&&gen===generation.current){halt();setError('Connection lost. Saved answers remain; finalized draft text stays in this tab. Reconnect or use typing.');}};
   });
   if(paused.current||gen!==generation.current){await closeMedia();throw new Error('Listening cancelled.');}
  }catch(e){stream.getTracks().forEach(t=>t.stop());if(socket){socket.onclose=null;socket.onmessage=null;socket.onerror=null;socket.close();}node?.disconnect();if(context&&context.state!=='closed')await context.close();media.current=null;throw e;}
 }
 async function speak(questionId,intro=false){
  const token=ctl.current.epoch,gen=generation.current;setStatus('ai-speaking');
  let blob;
  try{blob=await api('/v2/applications/'+live.current.application_id+(intro?'/intro':'/speech'),intro?{}:{question_id:questionId},true);}
  finally{if(!intro)await playbackState().catch(()=>{});}
  if(paused.current||gen!==generation.current||!ctl.current.canPlay(token))return false;
  return new Promise(resolve=>{
   const url=URL.createObjectURL(blob),audio=new Audio(url);sound.current={url,audio,resolve};
   audio.onended=()=>{if(gen!==generation.current){resolve(false);return;}if(!intro)ctl.current.playbackEnded(token);paint();sound.current=null;URL.revokeObjectURL(url);resolve(true);};
   audio.onerror=()=>{halt();setError('Audio playback failed. The server delivery counts toward the replay allowance. You can continue without replay or use typing.');resolve(false);};
   audio.play().catch(()=>{halt();setError('Browser blocked playback. Continue without replay or use typing; playback allowance counts server deliveries.');resolve(false);});
  });
 }
 function startChecks(){clearInterval(timer.current);timer.current=setInterval(()=>{if(!paused.current&&ctl.current.ready()&&!checking.current&&Date.now()>=retryAfter.current)considerEnd();},300);}
 async function begin(){
  halt();setError('');setBusy(true);setTyping(false);
  try{
   const f=await api('/v2/applications/'+live.current.application_id);live.current=f;setFlow(f);
   if(f.status==='completed'){setStatus('completed');return;}
   if(!f.active)throw new Error('The saved next question is still being prepared. Reload shortly.');
   const s=await playbackState(f),saved=preserved.current;
   ctl.current.begin();if(saved?.application===f.application_id&&saved.question===f.active.id)ctl.current.segments=new Map(saved.segments);
   paused.current=false;generation.current++;await openMic();
   if(!introDone.current&&!ctl.current.segments.size){const finished=await speak(null,true);if(!finished){halt();setError('Introduction interrupted. Reconnect when ready; no answer was submitted.');return;}introDone.current=true;await closeMedia();ctl.current.begin();await openMic();}
   startChecks();
   // Reconnect never consumes a replay automatically. Replays are explicit.
   if(s.initial_available&&!ctl.current.segments.size)await speak(f.active.id);
   else {ctl.current.state='listening';paint();}
  }catch(e){halt();setError(e.message);}finally{setBusy(false);}
 }
 async function replay(){
  if(busy||ctl.current.speaking||request.current||ctl.current.pending.size||checking.current)return;
  const s=await playbackState().catch(e=>{setError(e.message);return null;});
  if(!s||s.deliveries_remaining<=0)return;setBusy(true);setError('');
  try{
   if(paused.current){paused.current=false;generation.current++;ctl.current.state='listening';await openMic();startChecks();}
   ctl.current.epoch++;ctl.current.state='ai-speaking';await speak(live.current.active.id);
  }catch(e){halt();setError(e.message);}finally{setBusy(false);}
 }
 async function considerEnd(){
  if(checking.current||paused.current)return;checking.current=true;const c=ctl.current,token=c.prepare();if(token===null){checking.current=false;return;}
  const f=live.current,text=c.transcript();setStatus('processing');
  try{
   const verdict=await api('/v2/applications/'+f.application_id+'/end-check',{question_id:f.active.id,version:f.version,answer:text});
   if(paused.current||!c.canPlay(token))return;
   if(!verdict.complete){c.state='end-pending';retryAfter.current=Date.now()+15000;setStatus('listening');return;}
   await submit(text,token);
  }catch(e){if(!paused.current){c.state='end-pending';retryAfter.current=Date.now()+15000;setError(e.message);paint();}}finally{checking.current=false;}
 }
 async function submit(text,token=null){
  if(request.current||!text.trim()||text.length>6000)return;const f=live.current,gen=generation.current;
  request.current=crypto.randomUUID();setBusy(true);setStatus('saving');
  try{
   const next=await api('/v2/applications/'+f.application_id+'/answer',{event_id:request.current,version:f.version,question_id:f.active.id,answer:text});
   live.current=next;setFlow(next);request.current=null;await playbackState(next);
   if(next.status==='completed'){halt();preserved.current=null;ctl.current.complete();setStatus('completed');setDraft('');return;}
   if(paused.current||gen!==generation.current||(token!==null&&!ctl.current.canPlay(token))){return;}
   preserved.current=null;await closeMedia();ctl.current.begin();await openMic();setDraft('');await speak(next.active.id);
  }catch(e){halt();setError(e.message+' Reload saved state before retrying an ambiguous submission.');}
  finally{request.current=null;setBusy(false);}
 }
 async function finishExplicit(){const text=ctl.current.transcript();if(!text.trim()||ctl.current.speaking||ctl.current.pending.size){setError('Wait for speech and transcription to finish.');return;}await submit(text,ctl.current.epoch);}
 async function mapBank(role_id,bank){setBusy(true);try{await api('/admin/v2-banks',{role_id,bank});setBankData(await api('/admin/v2-banks'));setRoles(await api('/v2/roles'));}catch(e){setError(e.message);}finally{setBusy(false);}}
 async function showReport(aid){try{const result=await api('/admin/v2/reports/'+aid);setReports(rows=>rows.map(a=>a.id===aid?{...a,v2report:result.report}:a));}catch(e){setError(e.message);}}
 return <main className="role-admin"><header className="role-admin-head"><a href="/">← Existing applications / recruiter workspace</a><span>CONVERSATIONAL INTERVIEW · STAGING PILOT</span></header><h1>Your experience, in conversation.</h1>
  {error&&<p role="alert" className="role-error">{error}</p>}
  {!me?<p>Sign in on the main website, then return here. This pilot uses your existing account.</p>:!flow?<>
   <p>Six shared questions, then four role-specific questions. Up to two clarifiers per round. Existing four-question interviews remain on the main website.</p>
   {apps.length>0&&<section><h2>Resume a v2 interview</h2><p>Only applications created in this pilot can open here.</p>{apps.map(a=><button className="role-secondary" key={a.id} onClick={()=>load(a.id)}>{a.role_title}</button>)}</section>}
   <form onSubmit={create} className="role-editor"><h2>Start a new v2 application</h2><label>Role<select name="role_id" required>{roles.map(r=><option disabled={!r.bank} key={r.id} value={r.id}>{r.title}{!r.bank?' — bank mapping required':''}</option>)}</select></label><label>Relevant experience<textarea name="experience" minLength={20} maxLength={4000} required/></label>
    <label style={{display:'flex',gap:12,alignItems:'start'}}><input style={{width:24}} type="checkbox" required/>I agree to Sarvam processing my interview audio and answers, automatic listening/answer submission, and sharing my profile, transcript and advisory report with the hiring team in ClickUp. I can pause or use typing. Use fictional data for this staging pilot.</label><button disabled={busy}>Create interview</button></form>
   {bankData&&<section className="role-editor"><h2>Recruiter: domain bank mappings</h2><p>Applies to future v2 interviews only. Existing selections stay pinned.</p>{bankData.roles.map(r=><label key={r.id}>{r.title}<select value={r.bank||''} disabled={busy} onChange={e=>mapBank(r.id,e.target.value)}><option value="" disabled>Choose approved bank</option>{bankData.banks.map(b=><option key={b}>{b}</option>)}</select></label>)}
    <h2>Evidence reports</h2>{reports.map(a=><section key={a.id}><button className="role-secondary" onClick={()=>showReport(a.id)}>{a.name} · {a.role_title} — load report</button>{a.v2report&&<><p>{a.v2report.summary}</p>{a.v2report.criteria?.map(c=><div key={c.name}><h3>{c.name}</h3><p>{c.reason}</p><blockquote>{c.evidence||'No evidence supplied'}</blockquote><p>{c.source_id} · Confidence: {c.confidence||'not specified'}</p></div>)}</>}</section>)}</section>}
  </>:<section className="role-editor"><p className="role-kicker">{flow.active?.stage||'INTERVIEW COMPLETE'} · {flow.active?.kind||''} · {flow.answers.length} answers saved</p>
   <h2 aria-live="polite">{status==='ai-speaking'?'Interviewer is speaking…':status==='candidate-speaking'?'Listening…':status==='end-pending'?'Listening — take your time':status==='processing'?'Checking whether you have finished…':status==='saving'?'Saving your answer…':status==='completed'?'Interview submitted for human review':status==='paused'?'Interview paused':'Your turn — speak now'}</h2><h3>{flow.active?.text}</h3>
   {flow.status!=='completed'&&<><p>Use headphones to reduce echo. Short thinking pauses are allowed; Pause remains available. No camera is used.</p><p>Each question plays initially once, with up to <strong>2 replays</strong>. {allowance&&!allowance.initial_available?`${allowance.replays_remaining} replays remaining.`:'Initial playback available.'} A delivered audio response counts even if browser playback is interrupted.</p>
   <div className="role-actions"><button disabled={busy||status!=='paused'} onClick={begin}>Begin / resume listening</button><button className="role-secondary" disabled={busy||status==='candidate-speaking'||status==='processing'||status==='saving'||status==='ai-speaking'||!allowance||allowance.deliveries_remaining<=0} onClick={replay}>{allowance?.initial_available?'Hear question':`Hear again (${allowance?.replays_remaining??0} left)`}</button><button className="role-secondary" onClick={halt}>Pause listening</button><button className="role-secondary" disabled={busy||paused.current} onClick={finishExplicit}>I'm finished</button><button className="role-secondary" onClick={()=>{halt();setDraft(ctl.current.transcript());setTyping(true);}}>Use typing</button><button className="role-secondary" disabled={busy} onClick={()=>load(flow.application_id)}>Reload saved state</button></div>
   {typing?<form onSubmit={e=>{e.preventDefault();submit(draft);}}><label>Your answer<textarea required maxLength={6000} value={draft} onChange={e=>setDraft(e.target.value)}/></label><button disabled={busy||draft.length>6000}>Save typed answer</button></form>:<><p className="role-note">Finalized draft transcript (not saved until confirmed). A pause retains it in this tab; refreshing may lose unsaved speech.</p><p aria-live="off">{draft||'Your speech will appear here.'}</p></>}
   </>}
   <details><summary>Saved transcript</summary>{flow.answers.map(a=><section key={a.event_id}><h3>{a.stage} · {a.question}</h3><p>{a.answer}</p></section>)}</details>
  </section>}
 </main>;
}
