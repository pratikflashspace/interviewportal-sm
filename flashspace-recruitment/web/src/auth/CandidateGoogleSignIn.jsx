// Page-scoped addition: preserve the approved compact lilac/white login design.
// Like a streaming catalog's explicit next action, show one real provider action,
// never automatic One Tap/prompt or a pretend-success button.
import React,{useEffect,useRef,useState} from 'react';
import {Button} from '@kits/shadcn-ui';
import {googleRequest,loadGoogleSdk} from './candidate-google-client.mjs';
export default function CandidateGoogleSignIn({preview=false,disabled=false,onStart,onFinish,onSuccess}){
 const target=useRef(null),callbacks=useRef({onStart,onFinish,onSuccess});callbacks.current={onStart,onFinish,onSuccess};
 const [attempt,setAttempt]=useState(0),[state,setState]=useState('loading'),[message,setMessage]=useState('Checking Google sign-in…');
 useEffect(()=>{
  const controller=new AbortController();let alive=true,expiry,claimed=false;
  const fail=text=>{if(alive){target.current?.replaceChildren();setState('error');setMessage(text);}};
  async function initialize(){
   if(preview){setState('disabled');setMessage('Google sign-in preview — not connected.');return;}
   setState('loading');setMessage('Checking Google sign-in…');
   try{
    const config=await googleRequest('config',{signal:controller.signal});if(!alive)return;
    if(!config.enabled){setState('disabled');setMessage('Google sign-in pending configuration. Use email and password.');return;}
    const challenge=await googleRequest('challenge',{signal:controller.signal});
    const sdk=await loadGoogleSdk();if(!alive)return;
    const started=Date.now();
    sdk.initialize({client_id:challenge.client_id,nonce:challenge.nonce,auto_select:false,ux_mode:'popup',context:'signin',callback:async response=>{
     if(!alive||claimed)return;
     if(Date.now()-started>=290000){fail('Google sign-in expired. Try Google again.');return;}
     if(!response?.credential){fail('Google sign-in was not completed. You can use email and password.');return;}
     if(!callbacks.current.onStart())return;
     claimed=true;clearTimeout(expiry);setState('submitting');setMessage('Verifying Google sign-in…');
     try{const user=await googleRequest('login',{credential:response.credential,signal:controller.signal});if(alive)callbacks.current.onSuccess(user);}
     catch(error){fail(error.message);}
     finally{if(alive)callbacks.current.onFinish();}
    }});
    sdk.renderButton(target.current,{type:'standard',theme:'outline',size:'large',text:'continue_with',shape:'rectangular',width:Math.min(320,target.current.clientWidth||280)});
    setState('ready');setMessage('Google is for candidates only. Existing email/password accounts are not automatically linked.');
    expiry=setTimeout(()=>fail('Google sign-in expired. Try Google again.'),290000);
   }catch(error){fail(error.message);}
  }
  initialize();return()=>{alive=false;clearTimeout(expiry);controller.abort();target.current?.replaceChildren();};
 },[attempt,preview]);
 return <section aria-label="Candidate Google sign-in" style={{marginTop:20,display:'grid',gap:12}}>
  <div ref={target} hidden={disabled||state!=='ready'} style={{minHeight:state==='ready'?44:0}}/>
  <p className="login-preview-note" role="status">{message}</p>
  {state==='error'&&<Button type="button" variant="outline" disabled={disabled} onClick={()=>setAttempt(n=>n+1)}>Try Google again</Button>}
 </section>;
}
