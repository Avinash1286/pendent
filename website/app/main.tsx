import React from 'react';
import { createRoot } from 'react-dom/client';
import AuraExperience from '../components/aura-experience';
import './globals.css';

createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <AuraExperience />
  </React.StrictMode>,
);
