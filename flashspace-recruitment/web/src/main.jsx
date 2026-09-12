import React from 'react';
import {createRoot} from 'react-dom/client';
import './base.css';
import IntegratedInterview from './v2/IntegratedInterview.jsx';
import Workspace from './workspace/Workspace.jsx';
import LoginPage from './auth/LoginPage.jsx';
import './auth/login-readability.css';
const path=window.location.pathname.replace(/\/$/,'');
// Only these two approved login routes change. Signup/workspaces remain intact.
const loginRole=path==='/candidate/login'?'candidate':path==='/recruiter/login'?'recruiter':null;
createRoot(document.getElementById('root')).render(loginRole?<LoginPage role={loginRole}/>:path==='/interview-v2'?<IntegratedInterview/>:<Workspace/>);
