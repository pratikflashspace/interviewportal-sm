export const SECTIONS=[['personal','Personal details'],['summary','Professional summary'],['education','Education'],['experience','Experience'],['projects','Projects'],['skills','Skills'],['certifications','Certifications'],['links','Portfolio and professional links'],['preferences','Job preferences'],['resume','Resume link']];
// [key, label, type, maximum length, required]. Optional sections stay optional.
export const FIELDS={
 personal:[['name','Full name','text',100,true],['phone','Phone number','tel',40],['city','Current city','text',120],['headline','Professional headline','text',160]],
 summary:[['summary','Professional summary','textarea',2000]],
 education:[['qualification','Qualification','text',150,true],['institution','Institution','text',200,true],['specialization','Specialization','text',150],['start','Start year','text',4],['end','End year','text',4],['current','Currently studying','checkbox'],['grade','Grade or percentage (optional)','text',100]],
 experience:[['title','Job title','text',150,true],['company','Company or organization','text',200,true],['employment_type','Employment type','text',60],['start','Start date','month',7],['end','End date','month',7],['current','Currently working here','checkbox'],['responsibilities','Responsibilities','textarea',2000],['achievements','Achievements','textarea',2000]],
 projects:[['name','Project name','text',150,true],['description','Project description','textarea',2000],['contribution','Your personal contribution','textarea',2000],['technologies','Technologies used','text',500],['demo_url','Project or demo link','url',1000],['repository_url','Repository link','url',1000]],
 certifications:[['name','Certification name','text',150,true],['issuer','Issuer','text',200,true],['year','Year','text',4],['credential_url','Credential link','url',1000]],
 links:[['portfolio_url','Portfolio website','url',1000],['linkedin_url','LinkedIn URL','url',1000],['github_url','GitHub URL','url',1000]],
 preferences:[['roles','Preferred roles','text',500],['locations','Preferred locations','text',500],['work_mode','Preferred work mode','select',30],['employment_type','Preferred employment type','text',60],['availability','Availability or notice period','text',200]],
 resume:[['resume_url','Resume link (HTTPS)','url',1000]],
};
export const REPEAT=['education','experience','projects','certifications'];
export function newEntry(section){return Object.fromEntries(FIELDS[section].map(([k,,type])=>[k,type==='checkbox'?false:'']));}
export function safeHref(value){try{const u=new URL(value);return u.protocol==='https:'&&!u.username&&!u.password&&!/[\s\\]/.test(value)?value:null;}catch{return null;}}
export function profileResponse(value){
 if(value?.role!=='candidate'||typeof value.email!=='string'||!Number.isInteger(value.version)||value.version<0||!value.sections||!value.legacy||SECTIONS.some(([key])=>!value.sections[key]))throw Error('Profile response is incomplete. Please try again.');
 return value;
}
export async function profileRequest(path,{body,signal,fetcher=globalThis.fetch,timeoutMs=path==='/logout'?65000:30000}={}){
 if(!['/me','/workspace/candidate/profile','/logout'].includes(path))throw Error('Unsupported profile request.');
 const c=new AbortController(),abort=()=>c.abort();signal?.addEventListener('abort',abort,{once:true});if(signal?.aborted)c.abort();const timer=setTimeout(abort,timeoutMs);
 try{const r=await fetcher('/api'+path,{method:body===undefined?'GET':'POST',credentials:'same-origin',cache:'no-store',signal:c.signal,headers:{'X-Requested-With':'Flashspace',...(body===undefined?{}:{'Content-Type':'application/json'})},...(body===undefined?{}:{body:JSON.stringify(body)})});let value;try{value=await r.json();}catch{throw Error('Profile response was unreadable. Your unsaved input has been kept.');}
 if(!r.ok){const e=Error(r.status===409?'Profile changed in another session. Review the latest saved section before continuing.':r.status===401?'Your session expired. Sign in again before retrying.':r.status===403?'Candidate access is required.':r.status===400&&typeof value.error==='string'?value.error:r.status===429?'Too many saves. Please wait before retrying.':'Could not save or load your profile. Your unsaved input has been kept.');e.status=r.status;throw e;}return value;
 }catch(e){if(c.signal.aborted)throw Error(path==='/logout'?'Sign out is taking longer than expected. Wait a moment, refresh, and sign in again if needed.':'Profile request stopped or timed out. Check saved data before retrying; your unsaved input has been kept.');throw e;}
 finally{clearTimeout(timer);signal?.removeEventListener('abort',abort);}
}
