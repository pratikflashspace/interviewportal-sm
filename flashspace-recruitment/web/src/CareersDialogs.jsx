// Restore the original careers modal vocabulary, not the plain v2 fallback.
// Keep Manrope/Hind, paper/lilac surfaces, existing shared Dialog sizing and focus management.
import React from 'react';
import {ArrowRight,AudioLines} from 'lucide-react';
import {Button,Badge,Input,Textarea,Field,FieldGroup,FieldLabel,FieldDescription,Dialog,DialogContent,DialogTitle,DialogDescription,Checkbox,Alert,AlertDescription} from '@kits/shadcn-ui';

export async function submitCareerApplication(role, form, request=fetch){
 const consent=form.get('consent');
 if(consent!=='on'&&consent!=='true')throw Error('Please agree to the interview terms before applying.');
 const response=await request('/api/v2/applications',{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json','X-Requested-With':'Flashspace'},body:JSON.stringify({role_id:role.id,experience:form.get('experience'),portfolio:form.get('portfolio')||'',consent:true,consent_version:'flashspace-sarvam-conversation-v2'})});
 const result=await response.json();
 if(!response.ok)throw Error(result.error||'Unable to save your application. Please try again.');
 if(typeof result.application_id!=='string'||!result.application_id)throw Error('Application response was incomplete. Reopen My applications before retrying.');
 return result.application_id;
}

export default function CareersDialogs({selected,setSelected,applyRole,setApplyRole,user,auth,busy,error,setError,begin,apply}){
 return <>
 <Dialog open={!!selected} onOpenChange={v=>!v&&setSelected(null)}><DialogContent><DialogTitle>{selected?.title}</DialogTitle><DialogDescription>{selected?.location} · {selected?.type} · {selected?.experience}</DialogDescription>{selected&&<><Badge variant="secondary">Open role</Badge><p>{selected.description}</p><h3>What you’ll work on</h3><p>{selected.details}</p><div className="skills">{selected.skills.map(s=><span key={s}>{s}</span>)}</div><div className="soft-note"><AudioLines size={20}/><span>Apply with your profile, then join a two-stage AI interview. A person reviews your application.</span></div><Button disabled={busy} onClick={()=>begin(selected)}>Apply for this role <ArrowRight/></Button></>}</DialogContent></Dialog>
 <Dialog open={!!applyRole&&!!user&&!auth} onOpenChange={v=>{if(!v&&!busy){setApplyRole(null);setError('');}}}><DialogContent><DialogTitle>First, a little about you.</DialogTitle><DialogDescription>Applying for {applyRole?.title}. You can resume your interview later.</DialogDescription><form onSubmit={apply}><FieldGroup><Field><FieldLabel htmlFor="portfolio">Resume or portfolio link (optional)</FieldLabel><Input id="portfolio" name="portfolio" type="url" placeholder="https://…" maxLength={1000}/><FieldDescription>Use a link the hiring team can access. Files aren’t uploaded in this MVP.</FieldDescription></Field><Field><FieldLabel htmlFor="experience">Relevant experience</FieldLabel><Textarea id="experience" name="experience" required minLength={20} maxLength={4000} placeholder="What have you built, solved, or helped grow?"/></Field><Field><div className="consent-line"><Checkbox id="consent" name="consent" required/><FieldLabel htmlFor="consent">I agree to AI-assisted interviewing and to sharing my profile, saved answers and report with the hiring team in ClickUp.</FieldLabel></div><FieldDescription>Sarvam processes interview audio and text, including saved transcript drafts. Camera and microphone recording require separate consent inside the interview. Fictional staging data only; do not share sensitive personal information.</FieldDescription></Field>{error&&<Alert><AlertDescription>{error}</AlertDescription></Alert>}<Button type="submit" disabled={busy}>{busy?'Saving your application…':'Apply & start interview'}<ArrowRight/></Button></FieldGroup></form></DialogContent></Dialog>
 </>;
}
