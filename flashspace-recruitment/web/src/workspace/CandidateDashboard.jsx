// Approved Dashboard page only. Other workspace pages retain their current implementation.
import React,{useEffect,useRef,useState} from 'react';
import {Home,Search,FileText,Mic,UserRound,Settings,LifeBuoy,LogOut,ArrowRight,Briefcase,CheckCircle2} from 'lucide-react';
import CareersDialogs,{submitCareerApplication} from '../CareersDialogs';
import {request} from './Workspace';
import {candidateIdentity,dashboardRequest,dashboardMetrics,recommendationCards,greeting} from './candidate-dashboard.mjs';
import './candidate-dashboard.css';
const BASE='/candidate/workspace/';
const groups=[['Workspace',[['dashboard','Dashboard',Home],['jobs','Explore Jobs',Search],['applications','My Applications',FileText],['interviews','My Interviews',Mic],['profile','My Profile',UserRound],['resume','Resume',FileText]]],['Account',[['settings','Settings',Settings],['help','Help & Support',LifeBuoy]]]];
function DashboardBrand(){return <a className="cd-brand" href={BASE+'dashboard'} aria-label="Teamrecrut candidate dashboard"><span className="cd-mark" aria-hidden="true"><svg width="26" height="26" viewBox="0 0 24 24">{[[2,7],[6,12],[10,17],[14,12],[18,7]].map(([x,h])=><rect key={x} x={x} y={(24-h)/2} width="2" height={h} rx="1" fill="currentColor"/>)}</svg></span><span>teamrecrut<small>BY STIRRING MINDS</small></span></a>;}
function Card({label,value,detail,href,icon:Icon}){return <a className="cd-stat" href={href}><span className="cd-stat-label"><Icon size={19} aria-hidden="true"/>{label}</span><strong>{value}</strong><small>{detail}</small></a>;}
export default function CandidateDashboard(){
 const [user,setUser]=useState(null),[data,setData]=useState(null),[error,setError]=useState(''),[access,setAccess]=useState('checking'),[reload,setReload]=useState(0),[loading,setLoading]=useState(true);
 const [selected,setSelected]=useState(null),[applyRole,setApplyRole]=useState(null),[actionError,setActionError]=useState(''),[busy,setBusy]=useState(false);
 const appsRef=useRef(null);
 useEffect(()=>{
  const controller=new AbortController();let alive=true;const timer=setTimeout(()=>controller.abort(),20000);
  setLoading(true);setError('');setData(null);setSelected(null);setApplyRole(null);appsRef.current=null;
  async function load(){try{
   const identity=await dashboardRequest('/me',{signal:controller.signal});if(!alive)return;
   if(!candidateIdentity(identity)){setAccess('denied');setUser(null);return;}
   setAccess('allowed');setUser(identity);
   const [apps,profile,recommendations]=await Promise.all(['/workspace/candidate/applications','/workspace/profile','/workspace/candidate/recommendations'].map(path=>dashboardRequest(path,{signal:controller.signal})));
   const value={metrics:dashboardMetrics(apps,profile),recommendations:recommendationCards(recommendations)};
   if(alive)setData(value);
   // Prefetch the candidate applications list (role_id shape) so Apply opens
   // the form instantly. Idempotent apply makes a stale prefetch safe; begin()
   // still re-fetches when this has not landed yet. Silent on failure.
   request('/applications').then(rows=>{if(alive)appsRef.current=rows;}).catch(()=>{});
  }catch(e){if(alive){setError(e.name==='AbortError'?'Dashboard request timed out. Please try again.':e.message);if(e.status===401||e.status===403){setAccess('denied');setUser(null);}else if(!user)setAccess('error');}}
  finally{clearTimeout(timer);if(alive)setLoading(false);}}
  load();return()=>{alive=false;clearTimeout(timer);controller.abort();};
 },[reload]);
 async function logout(){if(busy)return;setBusy(true);try{await request('/logout',{});window.location.assign('/candidate/login');}catch(e){setActionError(e.message);setBusy(false);}}
 async function begin(role){setSelected(null);setActionError('');try{const apps=data?.applications||await request('/applications');const a=apps.find(item=>item.role_id===role.id);if(a){window.location.assign(a.flow_version===2?'/interview-v2?application='+encodeURIComponent(a.id):BASE+'legacy?application='+encodeURIComponent(a.id));return;}setApplyRole(role);}catch(e){setActionError(e.message);}}
 async function apply(e){e.preventDefault();if(busy)return;setBusy(true);setActionError('');try{const aid=await submitCareerApplication(applyRole,new FormData(e.currentTarget));window.location.assign('/interview-v2?application='+encodeURIComponent(aid));}catch(e){setActionError(e.message);}finally{setBusy(false);}}
 if(access!=='allowed')return <main className="cd-gate"><DashboardBrand/>{access==='checking'&&loading?<p role="status">Checking your candidate account…</p>:<><h1>{access==='denied'?'Candidate access required':'Dashboard unavailable'}</h1>{error&&<p role="alert">{error}</p>}<a href="/candidate/login">Sign in to your candidate account</a>{access==='error'&&<button onClick={()=>setReload(n=>n+1)}>Try again</button>}</>}</main>;
 const metrics=data?.metrics;
 return <div className="tr-shell cd-shell"><a className="cd-skip" href="#candidate-dashboard-content">Skip to dashboard</a><aside><DashboardBrand/>{groups.map(([group,links])=><nav key={group} aria-label={group}><p className="cd-nav-label">{group}</p>{links.map(([id,label,Icon])=><a key={id} href={BASE+id} aria-current={id==='dashboard'?'page':undefined}><Icon size={18} aria-hidden="true"/>{label}{id==='resume'&&<small>Link only</small>}</a>)}</nav>)}<p className="cd-resume-note">Resume links are supported. File upload is not available yet.</p><button className="cd-signout" onClick={logout} disabled={busy}><LogOut size={17} aria-hidden="true"/>Sign out</button></aside>
 <div className="tr-main"><header><span><span className="cd-breadcrumb">Workspace / </span>Dashboard</span><a href={BASE+'profile'}><UserRound size={17} aria-hidden="true"/>My Profile</a></header><main id="candidate-dashboard-content" tabIndex={-1}>
 <section className="cd-intro"><div><p className="tr-eyebrow">YOUR NEXT CHAPTER</p><h1>{greeting(new Date().getHours())}, {user.name}</h1><p>Find your next opportunity.</p></div><button className="cd-refresh" disabled={loading||busy} onClick={()=>setReload(n=>n+1)}>{loading?'Refreshing…':'Refresh dashboard'}</button></section>
 {loading&&<p role="status">Loading your dashboard…</p>}{error&&<div role="alert"><p>{error}</p><button disabled={loading} onClick={()=>setReload(n=>n+1)}>Try again</button></div>}{actionError&&<p role="alert">{actionError}</p>}
 {data&&<><section aria-label="Your dashboard totals" className="cd-stats">
 <Card icon={FileText} label="Applications" value={metrics.applications} detail="Submitted applications" href={BASE+'applications'}/>
 <Card icon={Mic} label="Interviews" value={metrics.completed+' / '+metrics.interviews} detail="Completed / total interviews" href={BASE+'interviews'}/>
 <Card icon={CheckCircle2} label="Shortlisted" value={metrics.shortlisted} detail="Currently shortlisted applications" href={BASE+'applications'}/>
 <Card icon={UserRound} label="Profile completeness" value={metrics.profile.percent+'%'} detail={metrics.profile.completed+' of '+metrics.profile.total+' sections filled'} href={BASE+'profile'}/>
 </section><details className="cd-completeness"><summary>How profile completeness is calculated</summary><p>Each section below counts equally when it contains saved text. This measures information supplied—not skills, eligibility or hiring suitability. Resume means a saved link, not an uploaded or verified file.</p><ul>{metrics.profile.sections.map(s=><li key={s.key}><span>{s.label}</span><strong>{s.complete?'Filled':'Not filled'}</strong></li>)}</ul><a href={BASE+'profile'}>Update My Profile <ArrowRight size={15} aria-hidden="true"/></a></details>
 {metrics.applications===0&&<section className="cd-welcome"><h2>Your next chapter starts here</h2><p>You haven’t submitted an application yet. Explore Stirring Minds roles to find an opportunity that interests you.</p><a href={BASE+'jobs'}>Explore Jobs <ArrowRight size={17} aria-hidden="true"/></a></section>}
 <section className="cd-recommendations"><div className="cd-section-heading"><div><h2>Recommended Jobs</h2><p>Stirring Minds roles sharing skills or a department with roles you’ve applied for. Not profile scoring or candidate ranking.</p></div><a href={BASE+'jobs'}>Explore all jobs <ArrowRight size={16} aria-hidden="true"/></a></div>
 {data.recommendations.length?<div className="tr-job-grid">{data.recommendations.map(({role,reason})=><article key={role.id}><p className="tr-eyebrow"><Briefcase size={15} aria-hidden="true"/> STIRRING MINDS</p><h3>{role.title}</h3><p>{role.location} · {role.type}</p><div className="skills">{role.skills.map(skill=><span key={skill}>{skill}</span>)}</div><p className="tr-note">{reason}</p><button onClick={()=>{setActionError('');setSelected(role);}}>View role <ArrowRight size={16} aria-hidden="true"/></button></article>)}</div>:<div className="cd-empty"><h3>{metrics.applications?'No similar openings right now':'Recommendations start with your first application'}</h3><p>{metrics.applications?'There are no other published Stirring Minds roles matching your applied roles. You can still browse all open jobs.':'Apply for a role to see other Stirring Minds opportunities with related skills or departments.'}</p><a href={BASE+'jobs'}>Browse open jobs <ArrowRight size={16} aria-hidden="true"/></a></div>}
 </section></>}
 <CareersDialogs {...{selected,setSelected,applyRole,setApplyRole,user,busy,begin,apply}} error={actionError} setError={setActionError} auth={false}/>
 </main></div></div>;
}
