import React from 'react';
import { createRoot } from 'react-dom/client';
import './base.css';
import App from './App.jsx';
import RoleManager from './RoleManager.jsx';
import Conversation from './v2/Conversation.jsx';
const path=window.location.pathname.replace(/\/$/,'');
createRoot(document.getElementById('root')).render(path==='/interview-v2'?<Conversation/>:path==='/recruiter/roles'?<RoleManager/>:<App/>);
