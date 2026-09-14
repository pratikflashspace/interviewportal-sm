// Explicit auth allowlist; no shared role, credentials in URLs or browser storage.
export function workspaceFor(user){if(user?.role==='candidate'&&user.admin===false)return '/candidate/workspace/dashboard';if(user?.role==='recruiter'&&user.admin===true)return '/recruiter/workspace/dashboard';throw Error('Account type could not be verified. Please sign in again.');}
export async function landingRequest(path,{body,signal,fetcher=globalThis.fetch}={}){
 if(!['/me','/roles','/auth/candidate/signup'].includes(path))throw Error('Unsupported landing request.');
 const c=new AbortController(),abort=()=>c.abort();signal?.addEventListener('abort',abort,{once:true});if(signal?.aborted)c.abort();const timer=setTimeout(abort,15000);
 try{const r=await fetcher('/api'+path,{method:body===undefined?'GET':'POST',credentials:'same-origin',cache:'no-store',signal:c.signal,headers:{'X-Requested-With':'Flashspace',...(body===undefined?{}:{'Content-Type':'application/json'})},...(body===undefined?{}:{body:JSON.stringify(body)})});
  if(!r.ok){const errors={400:'Check your name, email and password fields.',409:'This email is unavailable for registration. Try signing in instead.',429:'Too many attempts. Please wait before trying again.'};throw Error(errors[r.status]||'This service is unavailable. Please try again.');}
  try{return await r.json();}catch{throw Error('The service returned an unreadable response. Please try again.');}
 }catch(e){if(c.signal.aborted)throw Error('The request timed out or was cancelled. If you registered, try signing in before registering again.');throw e;}
 finally{clearTimeout(timer);signal?.removeEventListener('abort',abort);}
}
