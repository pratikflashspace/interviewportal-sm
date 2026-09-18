// Candidate presentation only. Dates/events are never inferred from AI results.
export const HIRING={applied:'Applied',under_review:'Under review',shortlisted:'Shortlisted',contacted:'Contacted',hired:'Hired',rejected:'Rejected'};
export const INTERVIEW={interview:'Available / in progress',completed:'Completed'};
export function validDate(value){return typeof value==='string'&&value.trim()&&Number.isFinite(Date.parse(value))?value:null;}
export function dateLabel(value){const date=validDate(value);return date?new Date(date).toLocaleDateString(undefined,{weekday:'short',year:'numeric',month:'short',day:'numeric'}):'Date not recorded';}
export function applicationsView(rows){
 if(!Array.isArray(rows))throw Error('Application data is unavailable. Please try again.');
 const ids=new Set();
 const result=rows.map(a=>{
  if(!a||typeof a.id!=='string'||!a.id||ids.has(a.id)||typeof a.role_title!=='string'||!a.role_title.trim()||typeof a.stage!=='string'||typeof a.interview_status!=='string'||!Array.isArray(a.events)||!Number.isInteger(a.version)||a.version<0)throw Error('Application data is unavailable. Please try again.');
  ids.add(a.id);
  const events=a.events.map(e=>{if(!e||typeof e.stage!=='string')throw Error('Application history is unavailable. Please try again.');return {stage:e.stage,created:validDate(e.created)};});
  return {id:a.id,role_title:a.role_title,created_at:validDate(a.created_at),interview_status:a.interview_status,stage:a.stage,version:a.version,flow_version:a.flow_version===2?2:a.flow_version===1?1:null,events};
 });
 return result.sort((a,b)=>(b.created_at?Date.parse(b.created_at):-Infinity)-(a.created_at?Date.parse(a.created_at):-Infinity)||a.id.localeCompare(b.id));
}
export function hiringLabel(a){
 // Existing API defaults completed interviews to under_review before a human
 // event exists. Distinguish that queue state from recorded recruiter review.
 return a.stage==='under_review'&&a.version===0?'Awaiting recruiter review':HIRING[a.stage]||'Status not recognized';
}
export function hiringKey(a){return a.stage==='under_review'&&a.version===0?'awaiting_review':a.stage;}
export function interviewLabel(a){return INTERVIEW[a.interview_status]||'Status not recognized';}
export function options(rows,kind){const get=kind==='hiring'?hiringKey:a=>a.interview_status;const label=kind==='hiring'?hiringLabel:interviewLabel;return [...new Map(rows.map(a=>[get(a),label(a)])).entries()].sort((a,b)=>a[1].localeCompare(b[1]));}
export function filterApplications(rows,query,hiring='',interview=''){const terms=query.trim().toLocaleLowerCase().split(/\s+/).filter(Boolean);return rows.filter(a=>terms.every(t=>a.role_title.toLocaleLowerCase().includes(t))&&(!hiring||hiringKey(a)===hiring)&&(!interview||a.interview_status===interview));}
export function timeline(a){
 const dated=[{label:'Application submitted',date:a.created_at,detail:'Your application was saved.'},...a.events.map(e=>({label:HIRING[e.stage]||'Recruiter status update',date:e.created,detail:e.stage==='contacted'?'Contacted status recorded; this does not confirm an email was sent.':'Recorded recruiter status.'}))];
 dated.sort((x,y)=>(x.date?Date.parse(x.date):Infinity)-(y.date?Date.parse(y.date):Infinity));
 return {events:dated,completion:a.interview_status==='completed'?{label:'Interview completed',date:null,detail:'Completion is confirmed by the saved interview status. Its completion date is not recorded by this endpoint.'}:null};
}
export function continuation(a){
 if(!a||a.interview_status!=='interview'||['rejected','hired'].includes(a.stage))return null;
 if(a.flow_version===2)return '/interview-v2?application='+encodeURIComponent(a.id);
 if(a.flow_version===1)return '/candidate/workspace/legacy?application='+encodeURIComponent(a.id);
 return null;
}
export async function applicationsRequest(path,{signal,fetcher=globalThis.fetch,timeoutMs=path==='/logout'?65000:12000}={}){
 if(!['/me','/workspace/candidate/applications','/logout'].includes(path))throw Error('Unsupported application request.');
 const c=new AbortController(),abort=()=>c.abort();signal?.addEventListener('abort',abort,{once:true});if(signal?.aborted)c.abort();const timer=setTimeout(abort,timeoutMs);
 try{const r=await fetcher('/api'+path,{method:path==='/logout'?'POST':'GET',credentials:'same-origin',cache:'no-store',signal:c.signal,headers:{'X-Requested-With':'Flashspace',...(path==='/logout'?{'Content-Type':'application/json'}:{})},...(path==='/logout'?{body:'{}'}:{})});
  if(!r.ok){const e=Error(r.status===401?'Your session has expired. Sign in again.':r.status===403?'Candidate access is required.':'Could not load your applications. Please try again.');e.status=r.status;throw e;}
  try{return await r.json();}catch{throw Error('Application data is unreadable. Please try again.');}
 }catch(e){if(c.signal.aborted)throw Error(path==='/logout'?'Sign out is taking longer than expected. Wait a moment, refresh, and sign in again if needed.':'Request stopped or timed out. Please try again.');throw e;}
 finally{clearTimeout(timer);signal?.removeEventListener('abort',abort);}
}
