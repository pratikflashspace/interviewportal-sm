import {applicationsView,continuation} from './my-applications.mjs';
export function interviewGroups(raw,search=''){
 const rows=applicationsView(raw),terms=search.trim().toLowerCase().split(/\s+/).filter(Boolean);
 const matching=rows.filter(a=>terms.every(t=>a.role_title.toLowerCase().includes(t)));
 return {total:rows.filter(a=>['interview','completed'].includes(a.interview_status)).length,
 active:matching.filter(a=>a.interview_status==='interview'),completed:matching.filter(a=>a.interview_status==='completed'),
 unknown:matching.filter(a=>!['interview','completed'].includes(a.interview_status))};
}
export function interviewAction(a){return continuation(a);}
export function applicationLink(a){return '/candidate/workspace/applications?application='+encodeURIComponent(a.id);}
