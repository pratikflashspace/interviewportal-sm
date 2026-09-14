import React from 'react';
import {createRoot} from 'react-dom/client';
import './base.css';
import IntegratedInterview from './v2/IntegratedInterview.jsx';
import Workspace from './workspace/Workspace.jsx';
import LoginPage from './auth/LoginPage.jsx';
import PublicLanding from './auth/PublicLanding.jsx';
import CandidateDashboard from './workspace/CandidateDashboard.jsx';
import ExploreJobs from './workspace/ExploreJobs.jsx';
import MyApplications from './workspace/MyApplications.jsx';
import MyInterviews from './workspace/MyInterviews.jsx';
import CandidateProfile from './workspace/CandidateProfile.jsx';
import './auth/login-readability.css';
import './workspace/resume-profile-only.css';
const path=window.location.pathname.replace(/\/$/,'');
if(path==='/candidate/workspace/resume'){
 window.location.replace('/candidate/workspace/profile#cp-title-resume');
}else{
 const loginRole=path==='/candidate/login'?'candidate':path==='/recruiter/login'?'recruiter':null;
 createRoot(document.getElementById('root')).render(path===''?<PublicLanding/>:loginRole?<LoginPage role={loginRole}/>:path==='/interview-v2'?<IntegratedInterview/>:path==='/candidate/workspace/dashboard'?<CandidateDashboard/>:path==='/candidate/workspace/jobs'?<ExploreJobs/>:path==='/candidate/workspace/applications'?<MyApplications/>:path==='/candidate/workspace/interviews'?<MyInterviews/>:path==='/candidate/workspace/profile'?<CandidateProfile/>:<Workspace/>);
}
