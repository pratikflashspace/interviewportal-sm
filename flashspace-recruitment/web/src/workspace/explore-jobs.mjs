// Saved public job fields only. No role writes, eligibility or candidate scoring.
export const MISSING='Not specified';
export const FILTERS=[['department','Department'],['experience','Experience'],['location','Location'],['work_mode','Work mode'],['type','Employment type'],['skills','Skills']];
export const WORK_MODES=['Remote','Hybrid','In office'];
// Canonical filter buckets: saved role text maps to Remote / Hybrid / In office so
// differently-worded but identical saved values ("Remote / On-site — both available"
// vs "Remote/On-site - Both Available") no longer appear as duplicate options.
// Missing work mode is never inferred from narrative location text.
export function workMode(role){
 const value=((role.work_mode||'')+' '+(role.location||'')).toLowerCase();
 if(!value.trim())return '';
 const hasRemote=value.includes('remote');
 const hasOffice=value.includes('on-site')||value.includes('onsite')||value.includes('office');
 if(value.includes('hybrid')||(hasRemote&&hasOffice))return 'Hybrid';
 if(hasRemote)return 'Remote';
 if(hasOffice)return 'In office';
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
 // Work mode filters on the canonical Remote / Hybrid / In office bucket; the
 // saved combined label stays visible on the role card. Missing work mode is
 // never inferred from narrative location text.
 if(key==='work_mode')return workMode(role)||MISSING;
 return display(role[key]);
}
export function filterOptions(roles,key){
 if(key==='work_mode')return [...WORK_MODES].filter(mode=>roles.some(r=>workMode(r)===mode));
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
export async function jobsRequest(path,{body,signal,fetcher=globalThis.fetch,timeoutMs=30000}={}){
 if(!['/me','/roles','/applications','/logout','/v2/applications'].includes(path))throw Error('Unsupported jobs request.');
 const c=new AbortController(),abort=()=>c.abort();signal?.addEventListener('abort',abort,{once:true});if(signal?.aborted)c.abort();const timer=setTimeout(abort,timeoutMs);
 try{
  const r=await fetcher('/api'+path,{method:body===undefined?'GET':'POST',credentials:'same-origin',cache:'no-store',signal:c.signal,headers:{'X-Requested-With':'Flashspace',...(body===undefined?{}:{'Content-Type':'application/json'})},...(body===undefined?{}:{body:JSON.stringify(body)})});
  let data;try{data=await r.json();}catch{throw Error('Service response was unreadable. Please try again.');}
  if(!r.ok){const e=Error(r.status===401?'Your session has expired. Sign in again.':r.status===403?'Candidate access is required.':r.status===409?'This role or application changed. Refresh jobs or open My Applications.':r.status===429?'Too many attempts. Please wait before trying again.':r.status===400?(typeof data.error==='string'?data.error:'Check your application details.'):'Could not load or save this request. Please try again.');e.status=r.status;throw e;}
  return data;
 }catch(e){if(c.signal.aborted)throw Error('Request stopped or timed out. For an application, check My Applications before retrying.');throw e;}
 finally{clearTimeout(timer);signal?.removeEventListener('abort',abort);}
}
