// Shared password input with a show/hide (eye) toggle.
// Accessible: labelled button with aria-pressed, does not submit the form.
import React,{useId,useState} from 'react';
import {Eye,EyeOff} from 'lucide-react';

export default function PasswordField({name,autoComplete,required=true,minLength=12,maxLength=128,disabled=false,placeholder='',className='lp-password',buttonClass='lp-visibility'}){
 const [visible,setVisible]=useState(false);
 const id=useId();
 return <span className={className}>
  <input id={id} name={name} type={visible?'text':'password'} autoComplete={autoComplete} required={required} minLength={minLength} maxLength={maxLength} disabled={disabled} placeholder={placeholder}/>
  <button type="button" className={buttonClass} aria-label={visible?'Hide password':'Show password'} aria-pressed={visible} aria-controls={id} disabled={disabled} onClick={()=>setVisible(v=>!v)}>{visible?<EyeOff size={18} aria-hidden="true"/>:<Eye size={18} aria-hidden="true"/>}</button>
 </span>;
}
