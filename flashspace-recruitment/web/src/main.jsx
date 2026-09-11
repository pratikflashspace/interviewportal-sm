import React from 'react';
import {createRoot} from 'react-dom/client';
import './base.css';
import IntegratedInterview from './v2/IntegratedInterview.jsx';
import Workspace from './workspace/Workspace.jsx';
const path=window.location.pathname.replace(/\/$/,'');
// WorkspaceApp/local harness must accompany this branch frontend. Not deployed.
createRoot(document.getElementById('root')).render(path==='/interview-v2'?<IntegratedInterview/>:<Workspace/>);
