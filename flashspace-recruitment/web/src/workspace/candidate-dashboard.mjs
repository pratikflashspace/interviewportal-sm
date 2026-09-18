// Display-only calculations on authenticated candidate APIs. No scoring/model calls.
export const PROFILE_SECTIONS=[['summary','Professional summary'],['education','Education'],['experience','Experience'],['skills','Skills'],['projects','Projects'],['preferences','Job preferences'],['resume_url','Resume link']];
export function greeting(hour){return hour<12?'Good morning':hour<17?'Good afternoon':'Good evening';}
export function candidateIdentity(user){return !!user&&user.role==='candidate'&&user.admin===false&&typeof user.name==='string';}
export function profileCompleteness(profile){
 if(profile?.role!=='candidate'||!profile.fields||typeof profile.fields!=='object')throw Error('Candidate profile is unavailable.');
 const sections=PROFILE_SECTIONS.map(([key,label])=>({key,label,complete:typeof profile.fields[key]==='string'&&profile.fields[key].trim().length>0}));
 const completed=sections.filter(s=>s.complete).length;
 return {sections,completed,total:sections.length,percent:Math.round(completed/sections.length*100)};
}
export function dashboardMetrics(apps,profile){
 if(!Array.isArray(apps)||apps.some(a=>!a||typeof a.id!=='string'||typeof a.interview_status!=='string'||typeof a.stage!=='string')||new Set(apps.map(a=>a.id)).size!==apps.length)throw Error('Application totals are unavailable.');
 const interviews=apps.filter(a=>['interview','completed'].includes(a.interview_status));
 return {applications:apps.length,interviews:interviews.length,completed:interviews.filter(a=>a.interview_status==='completed').length,shortlisted:apps.filter(a=>a.stage==='shortlisted').length,profile:profileCompleteness(profile)};
}
export async function dashboardRequest(path,{signal,fetcher=globalThis.fetch}={}){
 const allowed=['/me','/workspace/candidate/applications','/workspace/profile','/workspace/candidate/recommendations'];
 if(!allowed.includes(path))throw Error('Unsupported dashboard request.');
 // Fail fast (12s) so the page can offer a retry instead of hanging on
 // "Checking your candidate account..." when the backend is slow to wake.
 const c=new AbortController(),abort=()=>c.abort();signal?.addEventListener('abort',abort,{once:true});if(signal?.aborted)c.abort();
 const timer=setTimeout(abort,12000);
 try{
 const response=await fetcher('/api'+path,{signal:c.signal,credentials:'same-origin',cache:'no-store',headers:{'X-Requested-With':'Flashspace'}});
 if(!response.ok){const error=Error(response.status===401?'Your session has expired. Sign in again.':response.status===403?'Candidate access is required.':'Could not load dashboard data. Please try again.');error.status=response.status;throw error;}
 try{return await response.json();}catch{throw Error('Dashboard data is unavailable. Please try again.');}
 }finally{clearTimeout(timer);signal?.removeEventListener('abort',abort);}
}
export function recommendationCards(items){
 if(!Array.isArray(items))throw Error('Recommendations are unavailable.');
 return items.map(({role,reason})=>{
  if(!role||typeof role.id!=='string'||typeof role.title!=='string'||!Array.isArray(role.skills)||!role.skills.every(s=>typeof s==='string')||typeof reason!=='string')throw Error('Recommendations are unavailable.');
  // Explicit public display fields only: no internal versions/notes/evaluation.
  return {reason,role:Object.fromEntries(['id','title','department','location','type','experience','description','details','skills'].map(key=>[key,role[key]]))};
 });
}
