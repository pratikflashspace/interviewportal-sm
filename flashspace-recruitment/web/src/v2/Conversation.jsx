// Flashspace interview v2 pilot. Keep the existing Manrope/Hind, paper/lilac
// language; a prominent live state is the signature, not a fake recording card.
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
 const [status,setStatus]=useState('paused'),[error,setError]=useState(''),[draft,setDraft]=useState(''),[busy,setBusy]=useState(false),[typing,setTyping]=useState(false),[bankData,setBankData]=useState(null);
 const live=useRef(null),media=useRef(null),sound=useRef(null),ctl=useRef(new TurnController()),generation=useRef(0),checking=useRef(false),request=useRef(null),paused=useRef(true),timer=useRef(null),retryAfter=useRef(0),manual=useRef(false);
 useEffect(()=>{(async()=>{try{const u=await api('/me');setMe(u);if(u){setRoles(await api('/v2/roles'));setApps(await api('/applications'));if(u.admin)setBankData(await api('/admin/v2-banks'));}}catch(e){setError(e.message);}})();return()=>{halt();};},[]);
 function paint(){setStatus(ctl.current.state);setDraft(ctl.current.transcript());}
 function stopAudio(){if(sound.current){sound.current.audio.pause();URL.revokeObjectURL(sound.current.url);sound.current=null;}}
 function closeMedia(){const m=media.current;media.current=null;if(!m)return;m.socket.onclose=null;m.socket.close();m.stream.getTracks().forEach(t=>t.stop());m.node.disconnect();m.context.close();}
 function halt(){paused.current=true;generation.current++;ctl.current.pause();stopAudio();closeMedia();clearInterval(timer.current);setStatus('paused');}
 async function load(aid){halt();setError('');try{const f=await api('/v2/applications/'+aid);live.current=f;setFlow(f);setDraft('');}catch(e){setError(e.message);}}
 async function create(e){e.preventDefault();setBusy(true);setError('');try{const body=Object.fromEntries(new FormData(e.currentTarget));const f=await api('/v2/applications',{...body,consent:true,consent_version:consent});live.current=f;setFlow(f);setApps(await api('/applications'));}catch(e){setError(e.message);}finally{setBusy(false);}}
 async function openMic(){
  const stream=await navigator.mediaDevices.getUserMedia({audio:{echoCancellation:true,noiseSuppression:true,channelCount:1}});
  const context=new AudioContext({sampleRate:16000});
  if(context.sampleRate!==16000){stream.getTracks().forEach(t=>t.stop());await context.close();throw new Error('This browser cannot capture 16 kHz audio. Use typing for this test.');}
  let socket;
  try{
   await context.resume();await context.audioWorklet.addModule('/v2-pcm-worklet.js');
   socket=new WebSocket((location.protocol==='https:'?'wss:':'ws:')+'//'+location.host+'/api/v2/voice/'+live.current.application_id);
   const node=new AudioWorkletNode(context,'interview-pcm');const source=context.createMediaStreamSource(stream);const mute=context.createGain();mute.gain.value=0;source.connect(node);node.connect(mute);mute.connect(context.destination);
   media.current={stream,context,socket,node};
   node.port.onmessage=e=>{if(!paused.current&&socket.readyState===1){if(socket.bufferedAmount>64000){halt();setError('Network is too slow. Listening paused; unsaved speech may need repeating.');}else socket.send(e.data);}};
   await new Promise((resolve,reject)=>{const timeout=setTimeout(()=>reject(new Error('Voice connection timed out.')),20000);
    socket.onmessage=e=>{let msg;try{msg=JSON.parse(e.data);}catch{return;}
     if(msg.event==='ready'){clearTimeout(timeout);resolve();return;}
     if(msg.event==='error'){clearTimeout(timeout);reject(new Error(msg.message));halt();setError(msg.message);return;}
     if(paused.current)return;
     if(msg.event==='vad.speech_start'){ctl.current.speechStart(msg.utterance_idx);stopAudio();if(request.current){halt();setError('Speech resumed while an answer was saving. Reload the interview state before continuing; do not resubmit blindly.');return;}}
     if(msg.event==='vad.speech_end')ctl.current.speechEnd();
     if(msg.event==='transcript.partial')ctl.current.partial(msg.utterance_idx);
     if(msg.event==='transcript.final')ctl.current.final(msg.utterance_idx,msg.text);
     paint();
    };
    socket.onerror=()=>{clearTimeout(timeout);reject(new Error('Voice connection failed.'));};
    socket.onclose=()=>{clearTimeout(timeout);reject(new Error('Voice connection closed.'));if(!paused.current){halt();setError('Connection lost. Saved answers remain; reload and reconnect to continue.');}};
   });
  }catch(e){stream.getTracks().forEach(t=>t.stop());socket?.close();await context.close();media.current=null;throw e;}
 }
 async function speak(text,questionId){
  const token=ctl.current.epoch,gen=generation.current;
  setStatus('ai-speaking');
  const blob=await api('/v2/applications/'+live.current.application_id+'/speech',{question_id:questionId},true);
  if(paused.current||gen!==generation.current||!ctl.current.canPlay(token))return;
  const url=URL.createObjectURL(blob),audio=new Audio(url);sound.current={url,audio};
  audio.onended=()=>{if(gen!==generation.current)return;ctl.current.playbackEnded(token);paint();stopAudio();};
  audio.onerror=()=>{halt();setError('Audio playback failed. Use typing or reconnect.');};
  try{await audio.play();}catch{halt();setError('Browser blocked playback. Use Begin / reconnect to grant audio permission, or type.');}
 }
 async function begin(){
  halt();setError('');setBusy(true);setTyping(false);
  try{
   const f=await api('/v2/applications/'+live.current.application_id);live.current=f;setFlow(f);
   if(f.status==='completed'){setStatus('completed');return;}
   if(!f.active)throw new Error('The saved next question is still being prepared. Reload shortly.');
   ctl.current.begin();paused.current=false;generation.current++;await openMic();
   timer.current=setInterval(()=>{if(!paused.current&&ctl.current.ready()&&!checking.current&&Date.now()>=retryAfter.current)considerEnd();},300);
   await speak(f.active.text,f.active.id);
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
  if(request.current||!text.trim())return;
  const f=live.current,gen=generation.current;const event=crypto.randomUUID();request.current=event;setBusy(true);setStatus('saving');
  try{
   const next=await api('/v2/applications/'+f.application_id+'/answer',{event_id:event,version:f.version,question_id:f.active.id,answer:text});
   live.current=next;setFlow(next);
   if(next.status==='completed'){halt();ctl.current.complete();setStatus('completed');setDraft('');return;}
   if(paused.current||gen!==generation.current||(token!==null&&!ctl.current.canPlay(token)))return;
   closeMedia();ctl.current.begin();await openMic();setDraft('');await speak(next.active.text,next.active.id);
  }catch(e){halt();setError(e.message+' Reload saved state before retrying an ambiguous submission.');}
  finally{request.current=null;setBusy(false);}
 }
 async function finishExplicit(){
  const text=ctl.current.transcript();if(!text.trim()||ctl.current.speaking||ctl.current.pending.size){setError('Wait for speech and transcription to finish.');return;}
  const token=ctl.current.epoch;await submit(text,token);
 }
 async function mapBank(role_id,bank){setBusy(true);try{await api('/admin/v2-banks',{role_id,bank});setBankData(await api('/admin/v2-banks'));setRoles(await api('/v2/roles'));}catch(e){setError(e.message);}finally{setBusy(false);}}
 return <main className="role-admin"><header className="role-admin-head"><a href="/">← Existing applications / recruiter workspace</a><span>CONVERSATIONAL INTERVIEW · STAGING PILOT</span></header><h1>Your experience, in conversation.</h1>
  {error&&<p role="alert" className="role-error">{error}</p>}
  {!me?<p>Sign in on the main website, then return here. This pilot uses your existing account.</p>:!flow?<>
   <p>Six shared questions, then four role-specific questions. Up to two clarifiers per round. Existing four-question interviews remain on the main website.</p>
   {apps.length>0&&<section><h2>Resume a v2 interview</h2><p>Only applications created in this pilot can open here.</p>{apps.map(a=><button className="role-secondary" key={a.id} onClick={()=>load(a.id)}>{a.role_title}</button>)}</section>}
   <form onSubmit={create} className="role-editor"><h2>Start a new v2 application</h2><label>Role<select name="role_id" required>{roles.map(r=><option disabled={!r.bank} key={r.id} value={r.id}>{r.title}{!r.bank?' — bank mapping required':''}</option>)}</select></label><label>Relevant experience<textarea name="experience" minLength={20} maxLength={4000} required/></label>
    <label style={{display:'flex',gap:12,alignItems:'start'}}><input style={{width:24}} type="checkbox" required/>I agree to Sarvam processing my interview audio and answers, automatic listening/answer submission, and sharing my profile, transcript and advisory report with the hiring team in ClickUp. I can pause or use typing. Use fictional data for this staging pilot.</label>
    <button disabled={busy}>Create interview</button></form>
   {bankData&&<section className="role-editor"><h2>Recruiter: domain bank mappings</h2><p>Applies to future v2 interviews only. Existing selections stay pinned.</p>{bankData.roles.map(r=><label key={r.id}>{r.title}<select value={r.bank||''} disabled={busy} onChange={e=>mapBank(r.id,e.target.value)}><option value="" disabled>Choose approved bank</option>{bankData.banks.map(b=><option key={b}>{b}</option>)}</select></label>)}</section>}
  </>:<section className="role-editor">
   <p className="role-kicker">{flow.active?.stage||'INTERVIEW COMPLETE'} · {flow.active?.kind||''} · {flow.answers.length} answers saved</p>
   <h2 aria-live="polite">{status==='ai-speaking'?'Interviewer is speaking…':status==='candidate-speaking'?'Listening…':status==='end-pending'?'Listening — take your time':status==='processing'?'Checking whether you have finished…':status==='saving'?'Saving your answer…':status==='completed'?'Interview submitted for human review':status==='paused'?'Interview paused':'Your turn — speak now'}</h2>
   <h3>{flow.active?.text}</h3>
   {flow.status!=='completed'&&<><p>We begin with shared experience questions and then your role. Use headphones to reduce echo. Short thinking pauses are allowed; use Pause whenever needed. No camera is used.</p><div className="role-actions"><button disabled={busy||status!=='paused'} onClick={begin}>Begin / reconnect interview</button><button className="role-secondary" onClick={halt}>Pause listening</button><button className="role-secondary" disabled={busy||paused.current} onClick={finishExplicit}>I'm finished</button><button className="role-secondary" onClick={()=>{halt();setTyping(true);}}>Use typing</button><button className="role-secondary" disabled={busy} onClick={()=>load(flow.application_id)}>Reload saved state</button></div>
   {typing?<form onSubmit={e=>{e.preventDefault();submit(draft);}}><label>Your answer<textarea required maxLength={6000} value={draft} onChange={e=>setDraft(e.target.value)}/></label><button disabled={busy}>Save typed answer</button></form>:<><p className="role-note">Live transcript (not saved until the system confirms your turn):</p><p aria-live="off">{draft||'Your speech will appear here.'}</p></>}
   </>}
   <details><summary>Saved transcript</summary>{flow.answers.map(a=><section key={a.event_id}><h3>{a.stage} · {a.question}</h3><p>{a.answer}</p></section>)}</details>
  </section>}
 </main>;
}
