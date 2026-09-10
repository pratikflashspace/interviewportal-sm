// Temporary MVP: compact camera self-view beside the existing interview.
// Keep existing Manrope/Hind and lilac. Recording state and loss warning lead.
import React,{useEffect,useRef,useState} from 'react';
import './RecordingDock.css';
async function api(path,body){const r=await fetch('/api'+path,{method:body?'POST':'GET',credentials:'same-origin',headers:{'X-Requested-With':'Flashspace',...(body?{'Content-Type':'application/json'}:{})},...(body?{body:JSON.stringify(body)}:{})});const data=await r.json();if(!r.ok)throw Error(data.error||'Recording request failed.');return data;}
export default function RecordingDock(){
 const [user,setUser]=useState(null),[apps,setApps]=useState([]),[selected,setSelected]=useState(''),[open,setOpen]=useState(location.pathname==='/recordings'),[status,setStatus]=useState('idle'),[error,setError]=useState(''),[consent,setConsent]=useState(false),[items,setItems]=useState([]),[used,setUsed]=useState(0),[local,setLocal]=useState(null),[seconds,setSeconds]=useState(0);
 const camera=useRef(null),stream=useRef(null),recorder=useRef(null),run=useRef(null),download=useRef(null),timer=useRef(null),mounted=useRef(true);
 const selectedRef=useRef(selected);selectedRef.current=selected;
 useEffect(()=>{mounted.current=true;let active=true;async function refresh(){try{const u=await api('/me');if(!active)return;setUser(u);if(!u){stop();return;}const a=await api('/applications');if(!active)return;setApps(a);const current=run.current;if(current&&!current.startedCompleted&&a.find(x=>x.id===current.application)?.status==='completed')stop();if(u.admin){const list=await api('/recordings');if(active){setItems(list.recordings);setUsed(list.used);}}}catch{}}
 refresh();const interval=setInterval(refresh,5000);const unload=e=>{if(recorder.current?.state==='recording'||run.current?.uploading){e.preventDefault();e.returnValue='Recording/upload in progress.';}};window.addEventListener('beforeunload',unload);
 return()=>{active=false;mounted.current=false;clearInterval(interval);clearInterval(timer.current);window.removeEventListener('beforeunload',unload);if(recorder.current?.state==='recording')recorder.current.stop();stream.current?.getTracks().forEach(t=>t.stop());if(download.current)URL.revokeObjectURL(download.current);};},[]);
 useEffect(()=>{if(camera.current&&stream.current)camera.current.srcObject=stream.current;},[open,status]);
 function stop(){if(recorder.current?.state==='recording')recorder.current.stop();stream.current?.getTracks().forEach(t=>t.stop());clearInterval(timer.current);}
 async function refreshList(){try{const list=await api('/recordings');setItems(list.recordings);setUsed(list.used);}catch(e){setError(e.message);}}
 async function start(){
  setError('');if(!consent||!selected)return;setStatus('preparing');let media;
  try{
   if(!navigator.mediaDevices?.getUserMedia||!window.MediaRecorder)throw Error('Camera recording is not supported in this browser.');
   media=await navigator.mediaDevices.getUserMedia({video:{width:{ideal:640},height:{ideal:480},frameRate:{ideal:15,max:20}},audio:{echoCancellation:true,noiseSuppression:true}});
   const mime=['video/webm;codecs=vp8,opus','video/webm','video/mp4'].find(m=>MediaRecorder.isTypeSupported(m));if(!mime)throw Error('No supported recording format.');
   const slot=await api('/recordings',{application_id:selected,mime:mime.split(';')[0],consent:'temporary-av-v1'});
   const state={id:slot.id,application:selected,startedCompleted:apps.find(a=>a.id===selected)?.status==='completed',chunks:[],size:0,index:0,chain:Promise.resolve(),failed:false,uploading:true};run.current=state;
   const rec=new MediaRecorder(media,{mimeType:mime,videoBitsPerSecond:350000,audioBitsPerSecond:48000});stream.current=media;recorder.current=rec;if(camera.current)camera.current.srcObject=media;
   const post=async(index,chunk)=>{let last;for(let attempt=0;attempt<3;attempt++){try{const response=await fetch('/api/recordings/'+state.id+'/chunk/'+index,{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/octet-stream','X-Requested-With':'Flashspace'},body:chunk});if(!response.ok){const result=await response.json();throw Error(result.error||'Upload rejected.');}return;}catch(e){last=e;if(attempt<2)await new Promise(r=>setTimeout(r,1000*(attempt+1)));}}throw last;};
   rec.ondataavailable=e=>{if(!e.data.size)return;if(state.size+e.data.size>50*1024*1024){state.failed=true;stop();if(mounted.current)setError('50 MB limit reached. Only captured bytes retained below are available; recording stopped.');return;}state.size+=e.data.size;state.chunks.push(e.data);
    state.chain=state.chain.then(async()=>{for(let at=0;at<e.data.size;at+=1024*1024){await post(state.index,e.data.slice(at,at+1024*1024));state.index++;}}).catch(error=>{state.failed=true;stop();if(mounted.current)setError(error.message+' Keep the local download. Server upload is incomplete.');});};
   rec.onstop=async()=>{media.getTracks().forEach(t=>t.stop());clearInterval(timer.current);if(mounted.current)setStatus('uploading');
    const blob=new Blob(state.chunks,{type:mime});if(download.current)URL.revokeObjectURL(download.current);download.current=URL.createObjectURL(blob);if(mounted.current)setLocal({url:download.current,mime:mime.split(';')[0],size:blob.size});
    await state.chain;
    try{if(state.failed)throw Error('Recording is incomplete on the server. Keep the local download.');await api('/recordings/'+state.id+'/finish',{chunks:state.index});if(mounted.current)setStatus('saved');}
    catch(e){if(mounted.current){setError(e.message);setStatus('incomplete');}}finally{state.uploading=false;run.current=null;if(mounted.current)refreshList();}
   };
   rec.onerror=()=>{state.failed=true;stop();if(mounted.current)setError('Camera recording failed; retain available local video.');};
   media.getTracks().forEach(t=>t.onended=()=>{if(rec.state==='recording'){state.failed=true;stop();if(mounted.current)setError('Camera or microphone disconnected; recording stopped.');}});
   rec.start(2000);setSeconds(0);setStatus('recording');setOpen(true);let elapsed=0;timer.current=setInterval(()=>{elapsed++;setSeconds(elapsed);if(elapsed>=600){stop();setError('The 10-minute MVP recording limit was reached. Recording stopped; interview answers are separate.');}},1000);
  }catch(e){media?.getTracks().forEach(t=>t.stop());setError(e.message);setStatus('idle');}
 }
 async function remove(id){if(!confirm('Permanently remove this TEMPORARY server recording? Download it first.'))return;try{await api('/recordings/'+id+'/remove',{});await refreshList();}catch(e){setError(e.message);}}
 if(!user)return null;
 const active=['preparing','recording','uploading'].includes(status);
 return <aside className={'recording-dock '+(open?'is-open':'')} aria-label="Temporary interview recordings"><button className="recording-toggle" onClick={()=>setOpen(!open)}>{status==='recording'?'● Recording '+seconds+'s':user.admin?'MVP recordings':'Camera recording'} {open?'−':'+'}</button>{open&&<div className="recording-body"><h2>10-recording MVP</h2><p className="recording-warning">Temporary server storage. Download promptly: recordings may disappear after server replacement or redeploy. Fictional tests only.</p><p>Up to 10 stored/incomplete recordings, 50 MB each. Capture stops at 10 minutes. Camera + candidate microphone are recorded; interviewer audio is not guaranteed in this basic capture.</p>
 {error&&<p role="alert" className="recording-error">{error}</p>}
 <label>My test application<select disabled={active} value={selected} onChange={e=>setSelected(e.target.value)}><option value="">Choose application</option>{apps.map(a=><option key={a.id} value={a.id}>{a.role_title} · {a.status}</option>)}</select></label>
 <video ref={camera} muted autoPlay playsInline aria-label="Your live camera preview"/>
 <label className="recording-consent"><input type="checkbox" checked={consent} disabled={active} onChange={e=>setConsent(e.target.checked)}/>I agree to temporary audio/video recording and review by the authorized recruiter. I understand the storage may be lost.</label>
 <div className="recording-actions"><button disabled={active||!selected||!consent} onClick={start}>Enable camera & start recording</button><button disabled={status!=='recording'} onClick={stop}>Stop & finish upload</button></div>
 <p role="status">{status==='saved'?'Temporary server copy saved. Download a backup now.':status==='uploading'?'Finishing upload — keep this tab open.':status==='recording'?'Recording with camera preview. Continue the interview on the main page.':status}</p>
 {local&&<a href={local.url} download={'interview.'+(local.mime==='video/mp4'?'mp4':'webm')}>Download this browser’s recording</a>}
 {user.admin&&<section><h3>Recruiter review · {used}/10 slots</h3><button onClick={refreshList}>Refresh recordings</button>{items.map(m=><article key={m.id}><p>{m.created_at} · {m.status} · {(m.bytes/1048576).toFixed(1)} MB</p><p>Application: {m.application_id}</p>{m.status==='ready'&&<><video controls preload="none" src={'/api/recordings/'+m.id+'/media'}/><a href={'/api/recordings/'+m.id+'/media'} download>Download recording</a></>}<button onClick={()=>remove(m.id)}>Remove server copy</button></article>)}</section>}
 </div>}</aside>;
}
