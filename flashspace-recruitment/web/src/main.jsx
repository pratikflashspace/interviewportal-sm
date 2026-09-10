import React from 'react';
import { createRoot } from 'react-dom/client';
import './base.css';
import App from './App.jsx';
import RoleManager from './RoleManager.jsx';
import {RecordingReviewPage} from './InterviewRecordingReview.jsx';
const path=window.location.pathname.replace(/\/$/,'');
createRoot(document.getElementById('root')).render(path==='/recruiter/roles'?<RoleManager/>:path==='/recordings'?<RecordingReviewPage/>:<App/>);
