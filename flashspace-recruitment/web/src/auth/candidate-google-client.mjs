// GIS credentials travel only in a same-origin POST body; never URLs or storage.
const BASE='/api/auth/candidate/google';
export async function googleRequest(action,{credential,fetcher=globalThis.fetch,signal,timeoutMs=12000}={}){
 if(!['config','challenge','login'].includes(action))throw Error('Invalid sign-in action.');
 const controller=new AbortController();const abort=()=>controller.abort();
 signal?.addEventListener('abort',abort,{once:true});if(signal?.aborted)controller.abort();
 const timer=setTimeout(abort,timeoutMs);
 try{
  const response=await fetcher(action==='login'?BASE:BASE+'/'+action,{method:action==='config'?'GET':'POST',credentials:'same-origin',cache:'no-store',signal:controller.signal,
   headers:{'Content-Type':'application/json','X-Requested-With':'Flashspace'},...(action==='config'?{}:{body:JSON.stringify(action==='login'?{credential}:{})})});
  if(!response.ok){const messages={401:'Google sign-in expired or could not be verified. Try Google again.',403:'Google sign-in is for candidate accounts only. Reload if your session changed.',409:'Use email and password for this account, or sign out before trying Google. Accounts are not automatically linked.',429:'Too many sign-in attempts. Please wait before trying again.',503:'Google sign-in is unavailable. Use email and password.'};throw Error(messages[response.status]||'Google sign-in is unavailable. Use email and password.');}
  let result;try{result=await response.json();}catch{throw Error('Google sign-in returned an invalid response.');}
  if(action==='config'&&typeof result?.enabled!=='boolean')throw Error('Google sign-in configuration is unavailable.');
  if(action==='challenge'&&(!/^[\w-]+\.apps\.googleusercontent\.com$/.test(result?.client_id||'')||!/^[a-f0-9]{64}$/.test(result?.nonce||'')||result?.expires_in!==300))throw Error('Google sign-in configuration is unavailable.');
  if(action==='login'&&(result?.role!=='candidate'||result?.admin!==false))throw Error('Google sign-in did not return a candidate account.');
  return result;
 }catch(error){if(controller.signal.aborted){const e=Error('Google sign-in stopped or timed out. You can still use email and password.');e.name='AbortError';throw e;}if(error instanceof TypeError)throw Error('Could not connect to Google sign-in. Use email and password or try again.');throw error;}
 finally{clearTimeout(timer);signal?.removeEventListener('abort',abort);}
}
let sdkPromise;
export function loadGoogleSdk(){
 if(globalThis.google?.accounts?.id)return Promise.resolve(globalThis.google.accounts.id);
 if(sdkPromise)return sdkPromise;
 sdkPromise=new Promise((resolve,reject)=>{
  const script=document.createElement('script');script.src='https://accounts.google.com/gsi/client';script.async=true;script.defer=true;
  const timer=setTimeout(()=>fail(),10000);
  function fail(){clearTimeout(timer);script.remove();sdkPromise=null;reject(Error('Google could not load. Use email and password, or try again.'));}
  script.onerror=fail;script.onload=()=>{clearTimeout(timer);if(!globalThis.google?.accounts?.id){fail();return;}resolve(globalThis.google.accounts.id);};
  document.head.appendChild(script);
 });return sdkPromise;
}
