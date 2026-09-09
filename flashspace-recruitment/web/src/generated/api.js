export const LIVE = typeof window !== "undefined" && window.__FLASHSPACE_LIVE__ === true;
export const DEMO_ROLES = [
 {id:"growth",title:"Growth & Partnerships",department:"Growth",location:"New Delhi · Hybrid",type:"Full-time",experience:"1–3 years experience",description:"Turn conversations into partnerships. Help ambitious businesses find their next workspace.",details:"Build a partner pipeline, understand customer needs, and develop experiments that bring new businesses into the Flashspace community.",skills:["Business development","Partnerships","CRM"]},
 {id:"community",title:"Community Associate",department:"Community",location:"New Delhi · On-site",type:"Full-time",experience:"0–2 years experience",description:"Make every member feel at home. Create the connections that turn a space into a community.",details:"Support members day to day, coordinate community events and resolve operational issues with a thoughtful, practical approach.",skills:["Member experience","Events","Operations"]},
 {id:"engineering",title:"Full-stack Developer",department:"Engineering",location:"Remote · India",type:"Full-time",experience:"2–4 years experience",description:"Build useful things, end to end. Shape the digital tools that power a better workspace experience.",details:"Ship accessible customer interfaces, reliable APIs and internal tools. Work closely with operations to turn real user needs into software.",skills:["React","Python","APIs"]}
];
export const sampleAnswers = [
 "I built a member onboarding workflow for a coworking team. I mapped the first-week experience, interviewed five members, and tested a welcome checklist with the operations team.",
 "I first made the problem measurable. We tracked incomplete onboarding steps, tested a simpler checklist, and compared completion rates over two weeks.",
 "I would clarify the member’s needs, explain the options we can deliver, and agree on a specific next step. I would document the issue and follow up rather than promise something uncertain.",
 "I would compare onboarding completion and repeat support requests before and after the change. I would also ask members what still felt confusing and use that feedback for the next iteration."
];
const questions = [
 "Tell us about a project you’re proud of. What was your contribution?",
 "How did you approach the biggest challenge, and what did you learn?",
 "A customer needs something your team cannot deliver today. How would you handle the conversation?",
 "How would you measure whether your work made a meaningful difference?"
];
export const DEMO_APPLICANTS=[{id:"sample-01",name:"Demo Candidate 01",email:"demo@example.com",role_id:"growth",role_title:"Growth & Partnerships",status:"completed",created_at:"2026-09-09T08:00:00Z",answers:questions.map((q,i)=>({question:q,answer:sampleAnswers[i]})),sync_status:"Preview only",evaluation:{score:80,summary:"Fictional report: the sample answers describe a structured onboarding project, a measurable experiment and a practical customer response. Validate the claimed outcomes in human review.",criteria:[{name:"Relevant experience",score:4,reason:"A concrete project and personal contribution are described.",evidence:"I mapped the first-week experience, interviewed five members"},{name:"Problem solving",score:4,reason:"Uses a testable improvement rather than an unsupported assertion.",evidence:"We tracked incomplete onboarding steps, tested a simpler checklist"},{name:"Evidence of impact",score:4,reason:"Proposes meaningful measures; actual results still need verification.",evidence:"I would compare onboarding completion and repeat support requests"}]}}];
let memory={user:null,apps:[]};
try{memory=JSON.parse(sessionStorage.getItem("flashspace-preview")||"null")||memory;}catch{}
function persist(){try{sessionStorage.setItem("flashspace-preview",JSON.stringify(memory));}catch{}}
async function request(path,body,method="GET",raw=false){
 const res=await fetch(`/api${path}`,{method,credentials:"same-origin",headers:{"X-Requested-With":"Flashspace",...(body?{"Content-Type":raw?body.type:"application/json"}:{})},...(body?{body:raw?body:JSON.stringify(body)}:{})});
 if(!res.ok){let message="Something went wrong. Your saved progress is safe; please retry.";try{message=(await res.json()).error||message;}catch{}throw new Error(message);}
 return res;
}
async function json(path,body,method="GET"){return (await request(path,body,method)).json();}
function find(id){const a=memory.apps.find(a=>a.id===id);if(!a)throw new Error("Application not found.");return a;}
export const api={
 roles:()=>LIVE?json("/roles"):Promise.resolve(DEMO_ROLES),
 me:()=>LIVE?json("/me"):Promise.resolve(memory.user),
 auth:async(data,register)=>{if(LIVE)return json(register?"/register":"/login",data,"POST");memory.user={name:data.name||"Demo Candidate",email:data.email,admin:false};persist();return memory.user;},
 logout:async()=>{if(LIVE)return json("/logout",{},"POST");memory.user=null;persist();},
 apps:()=>LIVE?json("/applications"):Promise.resolve(memory.apps.filter(a=>a.email===memory.user?.email)),
 apply:async data=>{if(LIVE)return json("/applications",data,"POST");const role=DEMO_ROLES.find(r=>r.id===data.role_id);const old=memory.apps.find(a=>a.email===memory.user.email&&a.role_id===data.role_id);if(old)return old;const a={...data,id:crypto.randomUUID(),name:memory.user.name,email:memory.user.email,role_title:role.title,status:"interview",question:questions[0],answers:[],created_at:new Date().toISOString(),sync_status:"Preview only"};memory.apps.push(a);persist();return a;},
 answer:async(id,data)=>{if(LIVE)return json(`/applications/${id}/answer`,data,"POST");const a=find(id);if(data.turn!==a.answers.length)throw new Error("This answer was already saved. Reopen the application.");a.answers.push({question:a.question,answer:data.answer});a.question=questions[a.answers.length]||null;persist();return {...a};},
 finish:async id=>{if(LIVE)return json(`/applications/${id}/finish`,{},"POST");const a=find(id);a.status="completed";a.evaluation={score:null,summary:"Preview interview completed. The deployed app generates a real AI-assisted report.",criteria:[]};persist();return {...a};},
 adminApps:()=>LIVE?json("/admin/applications"):Promise.resolve([...memory.apps,...DEMO_APPLICANTS]),
 retry:id=>json(`/admin/applications/${id}/retry`,{},"POST"),
 transcribe:async(id,blob)=>(await request(`/applications/${id}/transcribe`,blob,"POST",true)).json(),
 speech:async id=>(await request(`/applications/${id}/speech`,{},"POST")).blob()
};
