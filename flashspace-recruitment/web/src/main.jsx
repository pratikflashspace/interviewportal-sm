import React from 'react';
import {createRoot} from 'react-dom/client';
import './base.css';
import App from './App.jsx';
import RoleManager from './RoleManager.jsx';
import IntegratedInterview from './v2/IntegratedInterview.jsx';
import InterviewReview from './v2/InterviewReview.jsx';
const path=window.location.pathname.replace(/\/$/,'');
createRoot(document.getElementById('root')).render(path==='/interview-v2'?<IntegratedInterview/>:path==='/interview-review'?<InterviewReview/>:path==='/recruiter/roles'?<RoleManager/>:<App/>);
