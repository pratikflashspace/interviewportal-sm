import React from 'react';
import { createRoot } from 'react-dom/client';
import './base.css';
import App from './App.jsx';
import RoleManager from './RoleManager.jsx';
import RecordingDock from './RecordingDock.jsx';
createRoot(document.getElementById('root')).render(<>{window.location.pathname.replace(/\/$/,'')==='/recruiter/roles'?<RoleManager/>:<App/>}<RecordingDock/></>);
