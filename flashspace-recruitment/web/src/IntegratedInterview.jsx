// Candidate interview, not a standalone recorder. Existing Manrope/Hind and
// paper/lilac UI: question + live self-view form one interview surface.
import React,{useEffect,useRef,useState} from 'react';
import {api,LIVE} from './generated/api';
import {InterviewMedia} from './interview-media.mjs';
import './IntegratedInterview.css';
async function call(path,body){const r=await fetch('/api'+path,{method:body?'POST':'GET',credentials:'same-origin',headers:{'X-Requested-With':'Flashspace',...(body?{'Content-Type':'application/json'}:{})},...(body?{body:JSON.stringify(body)}:{})});const data=await r.json();if(!r.ok)throw Error(data.error||'Interview request failed.');return data;}
export default function IntegratedInterview({application,onSaved,onComplete,onBack}){
 const [state,setState]=useState('precheck'),[consent,setConsent]=useState(false),[answer,setAnswer]=useState(''),[error,setError]=useState(''),[local,setLocal]=useState(null),[replays,setReplays]=useState(0);
 const a=useRef(application),media=useRef(null),video=useRef(null),mode=useRef('precheck'),alive=useRef(true),epoch=useRef(0),timer=useRef(null),rec=useRef(null),parts=useRef([]),text=useRef(''),chain=useRef(Promise.resolve()),speechSeen=useRef(false),lastSpeech=useRef(0),clipStart=useRef(0),clipVoiced=useRef(false),checkAfter=useRef(0),working=useRef(false),localUrl=useRef(null),turnToken=useRef(null),onSavedRef=useRef(onSaved),onCompleteRef=useRef(onComplete);
 a.current=application;onSavedRef.current=onSaved;onCompleteRef.current=onComplete;
 const show=s=>{mode.current=s;if(alive.current)setState(s);};
 const put=t=>{text.current=t;if(alive.current)setAnswer(t);};
 useEffect(()=>{alive.current=true;const unload=e=>{if(media.current&&!media.current.closed){e.preventDefault();e.returnValue='Interview recording is active.';}};window.addEventListener('beforeunload',unload);return()=>{alive.current=false;epoch.current++;clearInterval(timer.current);if(rec.current){rec.current.onstop=null;try{rec.current.stop();}catch{}}media.current?.finish();window.removeEventListener('beforeunload',unload);if(localUrl.current)URL.revokeObjectURL(localUrl.current);};},[]);
 useEffect(()=>{if(video.current&&media.current?.stream)video.current.srcObject=media.current.stream;},[state]);
 function fail(e){setError(typeof e==='string'?e:e.message);pause();}
 async function stopClip(transcribe=true){
  const current=rec.current;rec.current=null;if(!current)return;
  return new Promise(resolve=>{current.onstop=()=>{
   const blob=new Blob(current.collected,{type:current.mimeType});const voiced=current.voiced||clipVoiced.current;
   if(transcribe&&voiced&&blob.size>=100){chain.current=chain.current.then(async()=>{const result=await api.transcribe(a.current.id,blob);if(alive.current){const next=(text.current+' '+result.text).trim();if(next.length>6000)throw Error('Answer exceeds 6000 characters. Pause and review it before continuing.');put(next);}}).catch(e=>{if(alive.current)fail(e);});}
   resolve();};if(current.state==='recording')current.stop();else resolve();});
 }
 function startClip(){
  if(mode.current!=='listening'||rec.current||!media.current?.stream)return;
  const mime=['audio/webm','audio/mp4','audio/ogg'].find(t=>MediaRecorder.isTypeSupported(t));if(!mime)throw Error('Audio transcription format unavailable.');
  const r=new MediaRecorder(new MediaStream(media.current.stream.getAudioTracks()),{mimeType:mime});r.collected=[];r.voiced=false;r.ondataavailable=e=>{if(e.data.size)r.collected.push(e.data);};r.onerror=()=>fail('Microphone transcription failed.');r.start();rec.current=r;clipVoiced.current=false;clipStart.current=performance.now();
 }
 async function listen(){if(!media.current||media.current.closed)return;show('listening');speechSeen.current=false;lastSpeech.current=performance.now();startClip();}
 async function speak(replay=false){
  if(!media.current||media.current.closed||working.current)return;
  working.current=true;const token=++epoch.current;await stopClip(false);show('speaking');
  try{if(replay){if(replays>=2)throw Error('Two replays used for this question.');setReplays(n=>n+1);}const blob=await api.speech(a.current.id);if(token!==epoch.current||!alive.current)return;await media.current.play(blob);if(token===epoch.current&&alive.current)await listen();}
  catch(e){if(token===epoch.current){setError(e.message+' You can read the question and continue.');await listen();}}
  finally{working.current=false;}
 }
 async function begin(){
  if(!consent||working.current)return;working.current=true;setError('');show('preparing');const token=++epoch.current;
  const capture=new InterviewMedia({application:a.current.id,call,onFailure:message=>{if(alive.current)fail(message);}});media.current=capture;
  try{if(!LIVE)throw Error('Recording requires the hosted staging website.');const stream=await capture.start();if(!alive.current||token!==epoch.current){await capture.finish();return;}if(video.current)video.current.srcObject=stream;working.current=false;startMonitor();if(a.current.answers.length>=4){show('ready');return;}await speak();}
  catch(e){capture.dispose();working.current=false;show('paused');setError(e.message);}
 }
 function startMonitor(){clearInterval(timer.current);timer.current=setInterval(async()=>{
  if(!media.current||media.current.closed)return;const now=performance.now(),volume=media.current.level();
  if(mode.current==='listening'){
   if(volume>.025){speechSeen.current=true;lastSpeech.current=now;clipVoiced.current=true;if(rec.current)rec.current.voiced=true;}
   if(rec.current&&now-clipStart.current>=20000){show('rotating');await stopClip();if(mode.current==='rotating'){show('listening');startClip();}return;}
   if(speechSeen.current&&now-lastSpeech.current>=6000&&!working.current&&now>checkAfter.current){await endAnswer(false);}
  }else if(mode.current==='processing'&&volume>.025){lastSpeech.current=now;speechSeen.current=true;epoch.current++;show('listening');startClip();}
 },100);}
 async function endAnswer(explicit){
  if(working.current||mode.current!=='listening')return;
  if(!explicit&&!speechSeen.current)return;working.current=true;const token=++epoch.current;show('processing');
  try{await stopClip();await chain.current;if(token!==epoch.current||mode.current!=='processing')return;
   if(text.current.trim().length<10){checkAfter.current=performance.now()+15000;show('listening');startClip();return;}
   if(!explicit){const decision=await call('/applications/'+a.current.id+'/turn-ready',{turn:a.current.answers.length,answer:text.current});if(token!==epoch.current||mode.current!=='processing')return;if(!decision.complete){checkAfter.current=performance.now()+15000;show('listening');startClip();return;}}
   show('saving');const next=await api.answer(a.current.id,{turn:a.current.answers.length,answer:text.current});
   if(!alive.current)return;a.current=next;await onSavedRef.current(next);put('');setReplays(0);
   if(token!==epoch.current)return;
   if(next.answers.length>=4){working.current=false;await finishInterview();return;}
   working.current=false;await speak();
  }catch(e){if(alive.current){setError(e.message);await pause();}}finally{working.current=false;}
 }
 async function closeRecording(){const current=media.current;if(!current)return true;media.current=null;show('uploading');const result=await current.finish();if(result.blob.size){if(localUrl.current)URL.revokeObjectURL(localUrl.current);localUrl.current=URL.createObjectURL(result.blob);if(alive.current)setLocal({url:localUrl.current,mime:result.blob.type});}if(result.error){if(alive.current)setError(result.error);return false;}return true;}
 async function pause(){epoch.current++;show('pausing');clearInterval(timer.current);await stopClip();await chain.current;await closeRecording();if(alive.current)show('paused');working.current=false;}
 async function finishInterview(){
  epoch.current++;clearInterval(timer.current);await stopClip(false);const saved=await closeRecording();
  if(!saved){show('paused');return;}
  show('submitting');try{const result=await api.finish(a.current.id);show('complete');await onCompleteRef.current(result);}catch(e){show('ready');setError(e.message);}
 }
 async function leave(){await pause();onBack();}
 const active=['listening','speaking','processing','saving','rotating','ready'].includes(state);
 return <section className="integrated-interview"><header><span>{a.current.role_title}</span><span>{a.current.answers.length}/4 answers saved</span></header>
 <div className="integrated-grid"><section className="integrated-question"><p className="eyebrow">YOUR INTERVIEW</p><h1>{a.current.answers.length>=4?'Your answers are saved.':a.current.question}</h1><h2 role="status">{({precheck:'Ready when you are',preparing:'Checking camera and microphone…',speaking:'Interviewer is speaking…',listening:'Listening — take your time',rotating:'Listening…',processing:'Processing your answer…',saving:'Saving your answer…',pausing:'Pausing capture…',paused:'Interview paused',uploading:'Saving interview recording…',submitting:'Submitting interview…',complete:'Interview submitted',ready:'Ready to submit'})[state]}</h2>
 {!active&&['precheck','paused'].includes(state)&&<><p>Enable your camera and microphone once to begin this application’s interview. Your self-view stays here while the interviewer asks questions. Questions and candidate audio are mixed into this recording.</p><label className="integrated-consent"><input type="checkbox" checked={consent} onChange={e=>setConsent(e.target.checked)}/>I consent to audio/video recording and human recruiter review. This is a temporary staging recording; server replacement can erase it. Use fictional test data.</label><button disabled={!consent||working.current} onClick={begin}>{a.current.answers.length>=4?'Enable capture / complete upload':'Begin / resume interview'}</button></>}
 {active&&<div className="integrated-controls"><button onClick={pause} disabled={state==='saving'}>Pause interview</button><button disabled={state!=='listening'||working.current||replays>=2} onClick={()=>speak(true)}>Hear question again ({2-replays} left)</button><button disabled={state!=='listening'||working.current} onClick={()=>endAnswer(true)}>I’m finished answering</button></div>}
 {a.current.answers.length>=4&&['paused','ready'].includes(state)&&<button onClick={finishInterview}>Finish interview & submit</button>}
 {error&&<p role="alert" className="integrated-error">{error}</p>}
 <label htmlFor="interview-answer">Answer transcript</label><textarea id="interview-answer" value={answer} readOnly={state!=='listening'&&state!=='paused'} maxLength={6000} onChange={e=>put(e.target.value)} placeholder="Your speech is transcribed here. You can correct text while listening or paused."/>
 <p>Short pauses are allowed. Finalized text is saved when your answer is submitted. “I’m finished” is optional; there is no per-question start-recording step.</p>
 {local&&<a href={local.url} download={'interview-segment.'+(local.mime.includes('mp4')?'mp4':'webm')}>Download your recorded interview segment</a>}
 <button className="integrated-secondary" disabled={['preparing','saving','uploading','submitting','pausing'].includes(state)} onClick={leave}>Save captured segment & leave</button>
 </section><aside className="integrated-self"><video ref={video} muted autoPlay playsInline aria-label="Your interview camera preview"/><p>{active?'● Interview recording active':state==='uploading'?'Finishing upload':'Camera off until you begin'}</p><p>Self-view · private recruiter review</p><p className="integrated-warning">Temporary test storage: 10 slots, 50 MB per segment, 10 minutes per segment. Reaching a limit pauses the interview. Download important test recordings before redeploying.</p></aside></div></section>;
}
