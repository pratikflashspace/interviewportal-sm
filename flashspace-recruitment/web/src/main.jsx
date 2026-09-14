import React from 'react';
import {createRoot} from 'react-dom/client';
import './base.css';
import IntegratedInterview from './v2/IntegratedInterview.jsx';
import Workspace from './workspace/Workspace.jsx';
import LoginPage from './auth/LoginPage.jsx';
import CandidateDashboard from './workspace/CandidateDashboard.jsx';
import ExploreJobs from './workspace/ExploreJobs.jsx';
import MyApplications from './workspace/MyApplications.jsx';
import './auth/login-readability.css';
const path=window.location.pathname.replace(/\/$/,'');
// Only explicitly approved page routes change; recruiter and interview pages stay intact.
const loginRole=path==='/candidate/login'?'candidate':path==='/recruiter/login'?'recruiter':null;
createRoot(document.getElementById('root')).render(loginRole?<LoginPage role={loginRole}/>:path==='/interview-v2'?<IntegratedInterview/>:path==='/candidate/workspace/dashboard'?<CandidateDashboard/>:path==='/candidate/workspace/jobs'?<ExploreJobs/>:path==='/candidate/workspace/applications'?<MyApplications/>:<Workspace/>);
