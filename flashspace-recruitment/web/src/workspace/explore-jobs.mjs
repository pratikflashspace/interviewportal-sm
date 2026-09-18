// Saved public job fields only. No role writes, eligibility or candidate scoring.
export const MISSING='Not specified';
export const FILTERS=[['department','Department'],['work_mode','Work mode'],['type','Employment type'],['experience','Experience']];
export const WORK_MODES=['On site','Hybrid','Remote'];
export const EMPLOYMENT_TYPES=['Full time','Part time','Internship','Contract'];
// Work mode: On site is the default. Hybrid or Remote appear only when the
// saved role text explicitly states them; combined labels like "Remote /
// On-site — both available" read as On site (office-first hiring).
export function workMode(role){
 const value=role?((role.work_mode||'')+' '+(role.location||'')).toLowerCase():'';
 if(value.includes('hybrid'))return 'Hybrid';
 if(value.includes('remote')&&!value.includes('on-site')&&!value.includes('onsite')&&!value.includes('office'))return 'Remote';
 return 'On site';
}
export function employmentType(role){
 const value=(role.type||'').toLowerCase();
 if(!value.trim())return '';
 if(value.includes('intern'))return 'Internship';
 if(value.includes('contract')||value.includes('freelance')||value.includes('consult'))return 'Contract';
 if(value.includes('part'))return 'Part time';
 if(value.includes('full'))return 'Full time';
 return '';
}
export function display(value){return typeof value==='string'&&value.trim()?value:MISSING;}
export function publicRoles(items){
 if(!Array.isArray(items))throw Error('Open roles could not be read. Please try again.');
 const ids=new Set();return items.filter(r=>r?.published!==false&&(!r?.state||r.state==='published')).map(r=>{
  if(!r||typeof r.id!=='string'||!r.id||ids.has(r.id)||typeof r.title!=='string'||!r.title.trim()||!Array.isArray(r.skills)||!r.skills.every(s=>typeof s==='string'))throw Error('Open roles could not be read. Please try again.');
  ids.add(r.id);
  return Object.fromEntries(['id','title','department','location','type','experience','description','details','skills','work_mode','responsibilities','requirements','hiring_process'].map(k=>[k,k==='skills'?[...r.skills]:typeof r[k]==='string'?r[k]:'']));
 });
}
export function filterValue(role,key){
 // Work mode and employment type filter on canonical buckets; the saved label
 // stays visible on the role card. A pure city location is never a work mode.
 if(key==='work_mode')return workMode(role);
 if(key==='type')return employmentType(role)||MISSING;
 return display(role[key]);
}
export function filterOptions(roles,key){
 // Canonical options are always listed so future Part time / Internship /
 // Remote postings are filterable the moment they exist.
 if(key==='work_mode')return [...WORK_MODES];
 if(key==='type')return [...EMPLOYMENT_TYPES];
 return [...new Set(roles.flatMap(r=>key==='skills'?(r.skills.length?r.skills:[MISSING]):[filterValue(r,key)]))].sort((a,b)=>a.localeCompare(b));
}
export function matches(roles,search,filters={}){
 const terms=search.trim().toLocaleLowerCase().split(/\s+/).filter(Boolean);
 return roles.filter(r=>{
  const haystack=['title','department','location','type','experience','description','details','responsibilities','requirements','work_mode'].map(k=>r[k]||'').concat(r.skills).join(' ').toLocaleLowerCase();
  return terms.every(t=>haystack.includes(t))&&FILTERS.every(([key])=>!filters[key]||(key==='skills'?(r.skills.length?r.skills:[MISSING]).includes(filters[key]):filterValue(r,key)===filters[key]));
 });
}
export function existingDestination(apps,roleId){
 if(!Array.isArray(apps))throw Error('Could not check existing applications. Please try again.');
 const found=apps.find(a=>a?.role_id===roleId);if(!found)return null;
 if(typeof found.id!=='string'||!found.id)throw Error('Application data is unavailable. Open My Applications.');
 if(found.status==='completed')return '/candidate/workspace/applications';
 return (found.flow_version===2?'/interview-v2?application=':'/candidate/workspace/legacy?application=')+encodeURIComponent(found.id);
}
export async function jobsRequest(path,{body,signal,fetcher=globalThis.fetch,timeoutMs=path==='/logout'?65000:12000}={}){
 // 12s: fail fast on a stalled request so the page can offer a retry instead
 // of leaving the candidate on "Checking your candidate account..." for 30s.
 if(!['/me','/roles','/applications','/logout','/v2/applications'].includes(path))throw Error('Unsupported jobs request.');
 const c=new AbortController(),abort=()=>c.abort();signal?.addEventListener('abort',abort,{once:true});if(signal?.aborted)c.abort();const timer=setTimeout(abort,timeoutMs);
 try{
  const r=await fetcher('/api'+path,{method:body===undefined?'GET':'POST',credentials:'same-origin',cache:'no-store',signal:c.signal,headers:{'X-Requested-With':'Flashspace',...(body===undefined?{}:{'Content-Type':'application/json'})},...(body===undefined?{}:{body:JSON.stringify(body)})});
  let data;try{data=await r.json();}catch{throw Error('Service response was unreadable. Please try again.');}
  if(!r.ok){const e=Error(r.status===401?'Your session has expired. Sign in again.':r.status===403?'Candidate access is required.':r.status===409?'This role or application changed. Refresh jobs or open My Applications.':r.status===429?'Too many attempts. Please wait before trying again.':r.status===400?(typeof data.error==='string'?data.error:'Check your application details.'):'Could not load or save this request. Please try again.');e.status=r.status;throw e;}
  return data;
 }catch(e){if(c.signal.aborted)throw Error(path==='/logout'?'Sign out is taking longer than expected. Wait a moment, refresh, and sign in again if needed.':'Request stopped or timed out. For an application, check My Applications before retrying.');throw e;}
 finally{clearTimeout(timer);signal?.removeEventListener('abort',abort);}
}
