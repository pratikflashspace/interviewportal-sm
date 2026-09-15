// Manual login only. No credential persistence, logging, OAuth or automatic retry.
export const SERVICE_ERROR='Sign-in is temporarily unavailable. Please try again later.';
export function loginDestination(role){
 if(!['candidate','recruiter'].includes(role))throw Error('Choose an account type before signing in.');
 return '/'+role+'/workspace/dashboard';
}
export async function loginManually(role,credentials,{fetcher=globalThis.fetch,signal,timeoutMs=15000}={}){
 loginDestination(role);
 const controller=new AbortController();let timedOut=false;
 const abort=()=>controller.abort();
 signal?.addEventListener('abort',abort,{once:true});if(signal?.aborted)controller.abort();
 const timer=setTimeout(()=>{timedOut=true;controller.abort();},timeoutMs);
 try{
  const response=await fetcher('/api/auth/'+role+'/login',{method:'POST',credentials:'same-origin',cache:'no-store',signal:controller.signal,
   headers:{'Content-Type':'application/json','X-Requested-With':'Flashspace'},body:JSON.stringify({email:credentials.email.trim(),password:credentials.password})});
  if(response.status===401)throw Error('Email or password is incorrect for this account type.');
  if(response.status===429)throw Error('Too many sign-in attempts. Please wait before trying again.');
  if(!response.ok)throw Error(SERVICE_ERROR);
  let user;try{user=await response.json();}catch{throw Error(SERVICE_ERROR);}
  if(user?.role!==role||typeof user.admin!=='boolean'||user.admin!==(role==='recruiter'))throw Error(SERVICE_ERROR);
  return user;
 }catch(error){
  if(controller.signal.aborted){const e=Error(timedOut?'Sign-in timed out. Please try again.':'Sign-in cancelled.');e.name='AbortError';throw e;}
  if(error instanceof TypeError)throw Error('Unable to connect. Check your connection and try again.');
  throw error;
 }finally{clearTimeout(timer);signal?.removeEventListener('abort',abort);}
}
