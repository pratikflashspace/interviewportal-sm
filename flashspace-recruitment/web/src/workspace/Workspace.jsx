// Teamrecrut role-first workspaces. Preserve the approved identity, not a redesign.
// Manrope headings/Hind UI; violet #7044dd, lilac #ece5ff, paper #faf9fd, ink #241c38.
// Public entry -> role-specific auth -> own workspace; profile stays top-right.
import React,{useEffect,useState} from 'react';
import CareersDialogs,{submitCareerApplication} from '../CareersDialogs';
import RoleManager from '../RoleManager';
import {Interview} from '../generated/components';
import InterviewReview from '../v2/InterviewReview';
import {Settings,Resume,Company,Pipeline,Candidates,Analytics,Support} from './Features';
import '../generated/styles.css';
import './workspace.css';

export async function request(path,body){
 const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),30000);
 try{const r=await fetch('/api'+path,{signal:controller.signal,credentials:'same-origin',method:body===undefined?'GET':'POST',headers:{'X-Requested-With':'Flashspace',...(body===undefined?{}:{'Content-Type':'application/json'})},...(body===undefined?{}:{body:JSON.stringify(body)})});const value=await r.json();if(!r.ok)throw Error(value.error||'Request failed. Please try again.');return value;}finally{clearTimeout(timer);}
}
const labels={name:'Full name',phone:'Phone number',summary:'Professional summary',education:'Education',experience:'Experience',skills:'Skills',projects:'Projects',certifications:'Certifications',preferences:'Job preferences',resume_url:'Resume link (HTTPS)',designation:'Designation',bio:'About you'};
const go=path=>window.location.assign(path);
function Brand(){return <a className="brand" href="/">teamrecrut<span className="brand-sub">BY STIRRING MINDS</span></a>;}
function Auth({role,signup}){
 const [busy,setBusy]=useState(false),[error,setError]=useState('');
 async function submit(e){e.preventDefault();if(busy)return;setBusy(true);setError('');const data=Object.fromEntries(new FormData(e.currentTarget));try{await request('/auth/'+role+'/'+(signup?'signup':'login'),data);go('/'+role+'/workspace/dashboard');}catch(e){setError(e.message);}finally{setBusy(false);}}
 return <main className="tr-auth"><Brand/><a href="/account-type">← Choose account type</a><section><p className="tr-eyebrow">{role==='candidate'?'YOUR NEXT CHAPTER':'STIRRING MINDS · AUTHORISED ACCESS'}</p><h1>{signup?'Create your candidate account':'Welcome back'}</h1><p>{role==='candidate'?'Sign in to continue your job search.':'Sign in to manage your hiring workspace.'}</p><form onSubmit={submit}>{signup&&<label>Full name<input name="name" required minLength={2} maxLength={100} autoComplete="name"/></label>}<label>{role==='recruiter'?'Work email':'Email address'}<input name="email" type="email" required autoComplete="email"/></label><label>Password<input name="password" type="password" required minLength={12} maxLength={128} autoComplete={signup?'new-password':'current-password'}/></label>{signup&&<label>Confirm password<input name="confirm_password" type="password" required minLength={12} maxLength={128} autoComplete="new-password"/></label>}{error&&<p role="alert">{error}</p>}<button disabled={busy}>{busy?'Please wait…':signup?'Create candidate account':'Sign in'}</button></form>{role==='candidate'&&<a href={signup?'/candidate/login':'/candidate/signup'}>{signup?'Already have an account? Sign in':'Create a candidate account'}</a>}{role==='recruiter'&&<p className="tr-note">Access is restricted to the authorised Stirring Minds recruiter. No public signup.</p>}</section></main>;
}
function Profile({onSaved}){
 const [profile,setProfile]=useState(null),[error,setError]=useState(''),[notice,setNotice]=useState(''),[busy,setBusy]=useState(false);
 useEffect(()=>{request('/workspace/profile').then(setProfile).catch(e=>setError(e.message));},[]);
 async function save(e){e.preventDefault();if(busy)return;setBusy(true);setNotice('');setError('');try{const p=await request('/workspace/profile',{version:profile.version,fields:profile.fields});setProfile(p);setNotice('Profile saved.');onSaved(p);}catch(e){setError(e.message);}finally{setBusy(false);}}
 return <section><h1>My Profile</h1><p>Your details, kept with your account.</p>{error&&<p role="alert">{error}</p>}{notice&&<p role="status">{notice}</p>}{profile?<form className="tr-profile" onSubmit={save}><label>Email<input readOnly value={profile.email}/><small>Email and account type cannot be changed here.</small></label>{Object.entries(profile.fields).map(([k,v])=><label key={k}>{labels[k]||k}{['name','phone','resume_url','designation'].includes(k)?<input value={v} type={k==='resume_url'?'url':'text'} required={k==='name'} onChange={e=>setProfile({...profile,fields:{...profile.fields,[k]:e.target.value}})}/>:<textarea rows={3} value={v} onChange={e=>setProfile({...profile,fields:{...profile.fields,[k]:e.target.value}})}/>}</label>)}<button disabled={busy}>{busy?'Saving…':'Save profile'}</button></form>:!error&&<p>Loading profile…</p>}</section>;
}
function Jobs({user,recommendations=false,publicView=false}){
 const [items,setItems]=useState([]),[selected,setSelected]=useState(null),[applyRole,setApplyRole]=useState(null),[search,setSearch]=useState(''),[department,setDepartment]=useState('all'),[error,setError]=useState(''),[busy,setBusy]=useState(false),[loaded,setLoaded]=useState(false);
 useEffect(()=>{request(recommendations?'/workspace/candidate/recommendations':'/roles').then(r=>setItems(recommendations?r:r.map(role=>({role})))).catch(e=>setError(e.message)).finally(()=>setLoaded(true));},[recommendations]);
 async function begin(role){setSelected(null);if(publicView){go('/account-type');return;}try{const apps=await request('/applications');const a=apps.find(a=>a.role_id===role.id);if(a){go(a.flow_version===2?'/interview-v2?application='+encodeURIComponent(a.id):'/candidate/workspace/legacy?application='+encodeURIComponent(a.id));return;}setApplyRole(role);}catch(e){setError(e.message);}}
 async function apply(e){e.preventDefault();if(busy)return;setBusy(true);try{const aid=await submitCareerApplication(applyRole,new FormData(e.currentTarget));go('/interview-v2?application='+encodeURIComponent(aid));}catch(e){setError(e.message);}finally{setBusy(false);}}
 const filtered=items.filter(({role:r})=>(department==='all'||r.department===department)&&(r.title+' '+r.department+' '+r.location+' '+r.skills.join(' ')).toLowerCase().includes(search.toLowerCase()));
 return <section><h1>{recommendations?'Similar opportunities':'Explore jobs'}</h1><p>{recommendations?'Other Stirring Minds jobs related to roles you applied for.':'Find your next opportunity at Stirring Minds.'}</p><div className="tr-toolbar"><label>Search jobs, locations or skills<input type="search" value={search} onChange={e=>setSearch(e.target.value)}/></label><label>Department<select value={department} onChange={e=>setDepartment(e.target.value)}><option value="all">All departments</option>{[...new Set(items.map(x=>x.role.department))].map(d=><option key={d}>{d}</option>)}</select></label></div>{error&&<p role="alert">{error}</p>}<div className="tr-job-grid">{filtered.map(({role:r,reason})=><article key={r.id}><p className="tr-eyebrow">{r.department}</p><h2>{r.title}</h2><p>{r.location} · {r.type} · {r.experience}</p><p>{r.description}</p><div className="skills">{r.skills.map(s=><span key={s}>{s}</span>)}</div>{reason&&<p className="tr-note">{reason}</p>}<button onClick={()=>setSelected(r)}>View role →</button></article>)}</div>{loaded&&!filtered.length&&<p>{recommendations?'No similar opportunities yet. Recommendations appear when a published role shares skills or a department with your applications.':'No matching open roles.'}</p>}<CareersDialogs {...{selected,setSelected,applyRole,setApplyRole,user,busy,error,setError,begin,apply}} auth={false}/></section>;
}
function Dashboard({role,user}){
 const [apps,setApps]=useState(null),[jobs,setJobs]=useState(null),[error,setError]=useState('');
 useEffect(()=>{Promise.all([request('/workspace/'+role+'/applications'),request(role==='candidate'?'/roles':'/admin/roles')]).then(([a,j])=>{setApps(a);setJobs(j);}).catch(e=>setError(e.message));},[role]);
 return <section><p className="tr-eyebrow">{role==='candidate'?'YOUR NEXT CHAPTER':'YOUR HIRING WORKSPACE'}</p><h1>Hello, {user.name}</h1><p>{role==='candidate'?'Your opportunities and conversations, in one place.':'Manage Stirring Minds roles and review interview evidence.'}</p>{error&&<p role="alert">{error}</p>}{apps&&<dl className="tr-stats"><div><dt>Applications</dt><dd>{apps.length}</dd></div><div><dt>Completed interviews</dt><dd>{apps.filter(a=>a.interview_status==='completed').length}</dd></div><div><dt>Shortlisted</dt><dd>{apps.filter(a=>a.stage==='shortlisted').length}</dd></div><div><dt>{role==='candidate'?'Open roles':'Published jobs'}</dt><dd>{jobs.filter(r=>role==='candidate'||r.state==='published').length}</dd></div></dl>}<a href={'/'+role+'/workspace/'+(role==='candidate'?'jobs':'applications')}>{role==='candidate'?'Explore opportunities':'Review applications'} →</a>{role==='candidate'&&<Jobs user={user} recommendations/>}</section>;
}
function Legacy(){
 const [a,setA]=useState(null),[error,setError]=useState('');
 useEffect(()=>{const id=new URLSearchParams(location.search).get('application');request('/applications').then(items=>{const found=items.find(a=>a.id===id);if(!found)throw Error('Application not found.');setA(found);}).catch(e=>setError(e.message));},[]);
 if(error)return <p role="alert">{error}</p>;if(!a)return <p>Loading application…</p>;
 if(a.status==='completed')return <section><h1>{a.role_title}</h1><p>Your interview has been submitted for review.</p><a href="/candidate/workspace/applications">My Applications →</a></section>;
 return <Interview application={a} onSaved={setA} onComplete={setA} onBack={()=>go('/candidate/workspace/applications')}/>;
}
function Public(){return <main className="tr-public"><header><Brand/><nav><a href="#about">About</a><a href="#how">How it works</a><a href="#jobs">Open roles</a><a href="/account-type">Login / Sign up</a></nav></header><section className="hero"><div className="hero-copy"><p className="eyebrow">SMALL TEAMS. BIG POSSIBILITIES.</p><h1>Your next move.<br/><span>Make it matter.</span></h1><p>Find your opportunity with Stirring Minds.</p><div className="hero-actions"><a href="#jobs">Explore roles →</a><a href="/recruiter/login">Recruiter login →</a></div></div></section><section id="about"><h2>Different strengths. Shared ambition.</h2><p>Teamrecrut connects candidates with Stirring Minds roles through applications and conversational interviews.</p></section><section id="how"><h2>How it works</h2><p>Choose Candidate, create your account, explore a role and apply. Your saved application opens its interview, with consent and device checks before Begin. Authorised recruiters review the evidence and make hiring decisions.</p></section><section id="jobs"><Jobs publicView/></section></main>;}
export default function Workspace(){
 const path=location.pathname.replace(/\/$/,''),role=path.startsWith('/recruiter/')||path==='/interview-review'?'recruiter':'candidate';
 const [user,setUser]=useState(undefined),[error,setError]=useState('');
 useEffect(()=>{if(path.includes('/workspace/')||path==='/interview-review'||path==='/recruiter/roles')request('/me').then(setUser).catch(e=>{setError(e.message);setUser(null);});},[path]);
 if(!path)return <Public/>;
 if(path==='/account-type')return <main className="tr-entry"><Brand/><h1>How would you like to continue?</h1><p>Choose your Teamrecrut workspace.</p><div><a href="/candidate/login"><h2>Candidate</h2><p>Explore jobs, apply and meet your AI interviewer.</p><strong>Continue as Candidate →</strong></a><a href="/recruiter/login"><h2>Recruiter</h2><p>Authorised Stirring Minds hiring access.</p><strong>Continue as Recruiter →</strong></a></div><a href="/">Explore public roles</a></main>;
 if(path.endsWith('/login')||path==='/candidate/signup')return <Auth role={role} signup={path.endsWith('/signup')}/>;
 if(!path.includes('/workspace/')&&path!=='/interview-review'&&path!=='/recruiter/roles')return <main className="tr-entry"><h1>Page not found</h1><a href="/account-type">Choose account type</a></main>;
 if(user===undefined)return <main className="tr-entry">Checking your account…</main>;
 if(!user||user.role!==role)return <main className="tr-entry"><h1>{role==='candidate'?'Candidate':'Recruiter'} access required</h1>{error&&<p role="alert">{error}</p>}<a href={'/'+role+'/login'}>Sign in to this workspace</a></main>;
 const page=path==='/interview-review'?'review':path==='/recruiter/roles'?'jobs':path.split('/').pop(),base='/'+role+'/workspace/';
 const nav=role==='candidate'?[['dashboard','Dashboard'],['jobs','Explore Jobs'],['applications','My Applications'],['interviews','My Interviews'],['profile','My Profile'],['resume','Resume'],['settings','Settings'],['help','Help & Support']]:[['dashboard','Dashboard'],['jobs','Jobs'],['candidates','Candidates'],['applications','Applications'],['interviews','Interviews'],['analytics','Analytics'],['company','Company'],['settings','Settings'],['help','Help & Support']];
 async function logout(){try{await request('/logout',{});go('/account-type');}catch(e){setError(e.message);}}
 let content;
 if(page==='profile')content=<Profile onSaved={p=>setUser({...user,name:p.fields.name})}/>;
 else if(page==='dashboard')content=<Dashboard {...{role,user}}/>;
 else if(page==='settings')content=<Settings api={request} role={role}/>;
 else if(page==='help')content=<Support api={request} role={role}/>;
 else if(page==='jobs')content=role==='candidate'?<Jobs user={user}/>:<RoleManager/>;
 else if(['applications','interviews'].includes(page))content=<Pipeline api={request} role={role} interviews={page==='interviews'}/>;
 else if(role==='candidate'&&page==='resume')content=<Resume api={request}/>;
 else if(role==='candidate'&&page==='legacy')content=<Legacy/>;
 else if(role==='recruiter'&&page==='candidates')content=<Candidates api={request}/>;
 else if(role==='recruiter'&&page==='analytics')content=<Analytics api={request}/>;
 else if(role==='recruiter'&&page==='company')content=<Company api={request}/>;
 else if(role==='recruiter'&&page==='review')content=<InterviewReview/>;
 else content=<section><h1>Page not found</h1><a href={base+'dashboard'}>Return to dashboard</a></section>;
 return <div className="tr-shell"><aside><Brand/><p className="tr-eyebrow">{role.toUpperCase()} WORKSPACE</p><nav>{nav.map(([id,name])=><a key={id} href={base+id} aria-current={id===page?'page':undefined}>{name}</a>)}</nav><button onClick={logout}>Sign out</button></aside><div className="tr-main"><header><span>Stirring Minds</span><a href={base+'profile'}>My Profile</a></header>{error&&<p role="alert">{error}</p>}<main>{content}</main></div></div>;
}
