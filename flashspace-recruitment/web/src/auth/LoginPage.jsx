// Approved login-page scope: compact white card on lilac; no workspace sidebar.
// Teamrecrut waveform mark, Manrope headings/Hind UI, violet #7044dd.
// Google/recovery remain unavailable, not represented by non-working controls.
import React,{useEffect,useRef,useState} from 'react';
import {ArrowLeft,ArrowRight,Eye,EyeOff,ShieldCheck,UserRound} from 'lucide-react';
import {Button,Input,Field,FieldGroup,FieldLabel,Alert,AlertDescription} from '@kits/shadcn-ui';
import {loginManually,loginDestination} from './login-client.mjs';
import './login.css';
function LoginBrand(){return <div className="login-brand" aria-label="teamrecrut by Stirring Minds"><span className="login-mark"><svg width="24" height="24" viewBox="0 0 24 24" aria-hidden="true">{[[1.6,7.6],[5.8,12],[15.8,13],[20,7.2]].map(([x,h])=><rect key={x} x={x} y={(24-h)/2} width="2.6" height={h} rx="1.3" fill="currentColor"/>)}<circle cx="12" cy="4.5" r="2.6" fill="#d9f279"/><rect x="10.4" y="8.9" width="3.2" height="11.6" rx="1.6" fill="#d9f279"/></svg></span><span>teamrecrut<small>BY STIRRING MINDS</small></span></div>;}
const navigate=path=>window.location.assign(path);
export default function LoginPage({role='candidate',authenticate=loginManually,onSuccess=(_user,path)=>navigate(path),onNavigate=navigate,preview=false,previewEmpty=false}){
 const recruiter=role==='recruiter';
 const [visible,setVisible]=useState(false),[busy,setBusy]=useState(false),[error,setError]=useState(''),[fields,setFields]=useState({});
 const submitting=useRef(false),mounted=useRef(true),controller=useRef(null),emailRef=useRef(null),passwordRef=useRef(null);
 useEffect(()=>{mounted.current=true;return()=>{mounted.current=false;controller.current?.abort();};},[]);
 async function submit(e){
  e.preventDefault();if(submitting.current)return;
  const form=new FormData(e.currentTarget),email=String(form.get('email')||'').trim(),password=String(form.get('password')||'');
  const next={};if(!email)next.email='Enter your email address.';else if(!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)||email.length>254)next.email='Enter a valid email address.';
  if(!password)next.password='Enter your password.';else if(password.length<12||password.length>128)next.password='Use your existing 12–128 character password.';
  setFields(next);setError('');
  if(Object.keys(next).length){(next.email?emailRef:passwordRef).current?.focus();return;}
  submitting.current=true;setBusy(true);controller.current=new AbortController();
  try{const user=await authenticate(role,{email,password},{signal:controller.current.signal});if(!mounted.current)return;
   if(user?.role!==role||user.admin!==recruiter)throw Error('Sign-in is temporarily unavailable. Please try again later.');
   passwordRef.current.value='';setVisible(false);onSuccess(user,loginDestination(role));
  }catch(e){if(mounted.current)setError(e.message||'Unable to sign in. Please try again.');}
  finally{if(mounted.current)setBusy(false);submitting.current=false;}
 }
 function link(e,path){e.preventDefault();if(!busy)onNavigate(path);}
 if(!['candidate','recruiter'].includes(role))return <p role="alert">Choose Candidate or Recruiter before signing in.</p>;
 return <main className="login-page"><div className="login-wrap"><LoginBrand/>
 <a className="login-back" href="/account-type" aria-disabled={busy} onClick={e=>link(e,'/account-type')}><ArrowLeft size={16} aria-hidden="true"/>Back to account selection</a>
 <section className="login-card" aria-labelledby="login-title"><div className="login-role"><span>{recruiter?<ShieldCheck size={17} aria-hidden="true"/>:<UserRound size={17} aria-hidden="true"/>}{recruiter?'RECRUITER ACCESS':'CANDIDATE ACCOUNT'}</span></div>
 <h1 id="login-title">{recruiter?'Recruiter sign in':'Welcome back'}</h1><p className="login-subtitle">{recruiter?'Authorised Stirring Minds hiring access.':'Sign in to continue your job search.'}</p>
 {preview&&<p className="login-preview-note">Design preview · fictional details only. No real sign-in or data storage.</p>}
 <form onSubmit={submit} noValidate aria-busy={busy}><FieldGroup>
 <Field><FieldLabel htmlFor="login-email">{recruiter?'Work email':'Email address'}</FieldLabel><Input ref={emailRef} id="login-email" name="email" type="email" inputMode="email" autoComplete={preview?'off':'username'} required maxLength={254} disabled={busy} readOnly={preview} defaultValue={preview&&!previewEmpty?(recruiter?'recruiter@example.com':'candidate@example.com'):''} placeholder={recruiter?'Your authorised work email':'you@example.com'} aria-invalid={!!fields.email} aria-describedby={fields.email?'login-email-error':undefined}/>{fields.email&&<p className="login-field-error" id="login-email-error">{fields.email}</p>}</Field>
 <Field><FieldLabel htmlFor="login-password">Password</FieldLabel><div className="login-password"><Input ref={passwordRef} id="login-password" name="password" type={visible?'text':'password'} autoComplete={preview?'off':'current-password'} required minLength={12} maxLength={128} disabled={busy} readOnly={preview} defaultValue={preview&&!previewEmpty?'fictional-preview-only':''} placeholder="Enter your password" aria-invalid={!!fields.password} aria-describedby={fields.password?'login-password-error':undefined}/><button type="button" className="login-visibility" aria-label={visible?'Hide password':'Show password'} aria-pressed={visible} aria-controls="login-password" disabled={busy} onClick={()=>setVisible(v=>!v)}>{visible?<EyeOff size={19} aria-hidden="true"/>:<Eye size={19} aria-hidden="true"/>}</button></div>{fields.password&&<p className="login-field-error" id="login-password-error">{fields.password}</p>}</Field>
 {error&&<Alert variant="destructive"><AlertDescription>{error}</AlertDescription></Alert>}
 <Button type="submit" disabled={busy} className="login-submit">{busy?'Signing in…':'Sign in'}{!busy&&<ArrowRight aria-hidden="true"/>}</Button><span className="login-announcement" role="status">{busy?'Signing in. Please wait.':''}</span>
 </FieldGroup></form>
 {recruiter?<p className="login-restricted"><ShieldCheck size={16} aria-hidden="true"/>Only your authorised account can access this workspace.</p>:<p className="login-signup">New to Teamrecrut? <a href="/candidate/signup" aria-disabled={busy} onClick={e=>link(e,'/candidate/signup')}>Create candidate account</a></p>}
 </section><p className="login-footnote">{recruiter?'Private hiring workspace. No public registration.':'Your opportunities. Your applications. Your next chapter.'}</p>
 </div></main>;
}
