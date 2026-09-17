// Subject: Flashspace recruiters authoring vacancies, not a candidate demo.
// Design: an editorial job brief beside a compact vacancy index, borrowing a
// magazine's headline-first hierarchy rather than dashboard metric cards.
// Preserve Manrope/Hind and existing paper #faf9fd, ink #241c38, violet #7044dd,
// lilac #ece5ff; green #275024 means published, not decorative success.
import React, {useEffect, useState} from 'react';
import './RoleManager.css';

const fields = [
 ['title','Job title',200], ['department','Department',100],
 ['location','Location / work mode',200], ['type','Employment type',100],
 ['experience','Experience level',200], ['description','Short description',2000],
 ['details','Responsibilities and requirements',5000],
];
const empty = Object.fromEntries([...fields.map(([key])=>[key,'']),['skills','']]);

async function call(path, body) {
 const response=await fetch('/api'+path, {credentials:'same-origin',method:body?'POST':'GET',
  headers:{'X-Requested-With':'Flashspace',...(body?{'Content-Type':'application/json'}:{})},
  ...(body?{body:JSON.stringify(body)}:{})});
 let result; try { result=await response.json(); } catch { throw new Error('Could not read the server response. Reload before trying again.'); }
 if(!response.ok) throw new Error(result.error||'Unable to save. Please try again.');
 return result;
}

export default function RoleManager(){
 const [user,setUser]=useState(undefined),[roles,setRoles]=useState([]),[selected,setSelected]=useState(null);
 const [form,setForm]=useState(empty),[editing,setEditing]=useState(false),[preview,setPreview]=useState(false);
 const [busy,setBusy]=useState(false),[error,setError]=useState(''),[notice,setNotice]=useState(''),[filter,setFilter]=useState('all');
 useEffect(()=>{let mounted=true;(async()=>{try{const u=await call('/me');if(!mounted)return;setUser(u);if(u?.admin){const r=await call('/admin/roles');if(mounted)setRoles(r);}}catch(e){if(mounted){setError(e.message);setUser(null);}}})();return()=>{mounted=false;};},[]);
 function open(role){setSelected(role);setForm(role?{...role,skills:role.skills.join(', ')}:{...empty});setEditing(true);setPreview(false);setError('');setNotice('');}
 async function reload(){setBusy(true);setError('');try{setRoles(await call('/admin/roles'));setEditing(false);setNotice('Roles reloaded. Open a role to edit its latest version.');}catch(e){setError(e.message);}finally{setBusy(false);}}
 async function save(e){e.preventDefault();setBusy(true);setError('');setNotice('');try{
  const body=Object.fromEntries(fields.map(([key])=>[key,form[key]]));body.skills=form.skills.split(',').map(s=>s.trim()).filter(Boolean);
  if(selected)body.version=selected.version;
  const role=await call(selected?'/admin/roles/'+selected.id:'/admin/roles',body);
  setRoles(previous=>selected?previous.map(r=>r.id===role.id?role:r):[...previous,role]);setSelected(role);setForm({...role,skills:role.skills.join(', ')});
  setNotice(role.state==='published'?'Published role updated for new applicants. Existing interviews are unchanged.':'Role saved. It is not accepting applications unless published.');
 }catch(e){setError(e.message);}finally{setBusy(false);}}
 async function changeState(role,state){
  const action=state==='published'?'Publish this saved role and allow new applications?':state==='closed'?'Close new applications? Existing interviews will remain available.':'Move this role to draft and hide it from new applicants?';
  if(!window.confirm(action))return;setBusy(true);setError('');setNotice('');
  try{const updated=await call('/admin/roles/'+role.id+'/state',{version:role.version,state});setRoles(items=>items.map(r=>r.id===role.id?updated:r));
   if(selected?.id===role.id){setSelected(updated);setForm({...updated,skills:updated.skills.join(', ')});setPreview(false);}
   setNotice(state==='published'?'Role published. Candidates can now apply.':state==='closed'?'Applications closed. Existing records are preserved.':'Role moved to draft.');
  }catch(e){setError(e.message);}finally{setBusy(false);}
 }
 if(user===undefined)return <main className="role-admin"><p role="status">Loading recruiter access…</p></main>;
 if(!user?.admin)return <main className="role-admin"><a href="/">← Back to website / log in</a><h1>Recruiter access required</h1><p>Log in on the website with an existing recruiter account, then open Manage roles.</p>{error&&<p role="alert">{error}</p>}</main>;
 const visible=roles.filter(r=>filter==='all'||r.state===filter);
 return <main className="role-admin">
  <header className="role-admin-head"><a href="/">← Back to recruitment website</a><span>FLASHSPACE / RECRUITER TOOLS</span></header>
  <section className="role-admin-title"><div><p className="role-kicker">BUILD YOUR NEXT TEAM</p><h1>Manage roles</h1><p>Write the brief. Review it. Open the opportunity.</p></div><button type="button" disabled={busy} onClick={()=>open(null)}>+ Add role</button></section>
  {error&&<p className="role-error" role="alert">{error}</p>}{notice&&<p className="role-notice" role="status">{notice}</p>}
  <div className="role-admin-layout"><aside className="role-index" aria-label="Saved roles"><div className="role-index-tools"><label>Status <select value={filter} onChange={e=>setFilter(e.target.value)}><option value="all">All roles</option><option value="draft">Draft</option><option value="published">Published</option><option value="closed">Closed</option></select></label><button className="role-secondary" disabled={busy} onClick={reload}>Reload</button></div>
   {visible.map(role=><button type="button" className={'role-index-item '+(selected?.id===role.id?'role-active':'')} key={role.id} disabled={busy} onClick={()=>open(role)}><span className={'role-state '+role.state}>{role.state}</span><strong>{role.title}</strong><small>{role.department} · {role.location}</small></button>)}
   {!visible.length&&<p>No roles in this view. Add a role or change the status filter.</p>}
  </aside><section className="role-editor" aria-label="Role editor">
   {!editing?<div className="role-editor-empty"><h2>A clear brief starts here.</h2><p>Select a vacancy to edit, or add a new role. New roles begin as drafts.</p><p>Closing a role preserves its applications, interview history and ClickUp records.</p></div>:<>
    <div className="role-editor-heading"><h2>{selected?'Edit role':'New role'}</h2><span className={'role-state '+(selected?.state||'draft')}>{selected?.state||'draft'}</span></div>
    <p className="role-note">{selected?.state==='published'?'Saving changes updates this published vacancy for new applicants. Existing interview requirements stay unchanged.':'Save a complete draft, preview it, then publish when ready.'}</p>
    <form onSubmit={save}><div className="role-fields">{fields.map(([key,label,max])=><label className={key==='description'||key==='details'?'role-wide':''} key={key} htmlFor={'role-'+key}>{label}{key==='description'||key==='details'?<textarea id={'role-'+key} required maxLength={max} rows={key==='details'?6:3} value={form[key]} disabled={busy} onChange={e=>setForm({...form,[key]:e.target.value})}/>:<input id={'role-'+key} required maxLength={max} value={form[key]} disabled={busy} onChange={e=>setForm({...form,[key]:e.target.value})}/>}</label>)}<label className="role-wide" htmlFor="role-skills">Skills, separated by commas<input id="role-skills" required value={form.skills} disabled={busy} onChange={e=>setForm({...form,skills:e.target.value})}/><small>1–20 skills, up to 100 characters each.</small></label></div>
     <div className="role-actions"><button type="submit" disabled={busy}>{busy?'Saving…':selected?'Save changes':'Save draft'}</button><button type="button" className="role-secondary" disabled={busy} onClick={()=>setPreview(!preview)}>{preview?'Hide preview':'Preview wording'}</button><button type="button" className="role-secondary" disabled={busy} onClick={()=>{setEditing(false);setSelected(null);}}>Cancel</button></div>
    </form>
    {preview&&<article className="role-preview"><p className="role-kicker">WORDING PREVIEW · MAY INCLUDE UNSAVED CHANGES</p><h2>{form.title||'Job title'}</h2><p>{form.location} · {form.type} · {form.experience}</p><p>{form.description}</p><h3>Responsibilities and requirements</h3><p className="role-prewrap">{form.details}</p><p>{form.skills}</p></article>}
    {selected&&<section className="role-publish"><h3>Availability</h3><p>These actions use the last saved version. Save edits first.</p><div className="role-actions">{selected.state!=='published'&&<button disabled={busy} onClick={()=>changeState(selected,'published')}>Publish saved role</button>}{selected.state!=='closed'&&<button className="role-secondary" disabled={busy} onClick={()=>changeState(selected,'closed')}>Close applications</button>}{selected.state!=='draft'&&<button className="role-secondary" disabled={busy} onClick={()=>changeState(selected,'draft')}>Move to draft</button>}</div></section>}
   </>}
  </section></div><footer className="role-admin-foot">Role identities stay stable. Existing applications keep their original requirements. ClickUp Lists are created through application sync, not by this editor.</footer>
 </main>;
}
