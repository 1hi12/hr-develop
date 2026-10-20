import React from 'react';
import ReactDOM from 'react-dom/client';
import { createRouter, RouterProvider } from '@tanstack/react-router';
import { QueryClientProvider } from '@tanstack/react-query';
import { PublicClientApplication } from '@azure/msal-browser';
import { routeTree } from './routeTree.gen';
import { queryClient } from './lib/query/queryClient';
import { msalConfig } from './lib/msalConfig';
import './index.css';
import { Toaster } from 'sonner';
import { LanguageProvider } from './contexts/LanguageContext';
import { WebSocketProvider } from './contexts/WebSocketContext';

const router = createRouter({
  routeTree,
  context: {
    queryClient,
  },
});

declare module '@tanstack/react-router' {
  interface Register {
    router: typeof router;
  }
}

const msalInstance = new PublicClientApplication(msalConfig);

// Initialize MSAL and handle redirects
msalInstance.initialize().then(() => {
  msalInstance.handleRedirectPromise().catch((error) => {
    console.error('MSAL redirect error:', error);
  });
});

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <LanguageProvider>
      <QueryClientProvider client={queryClient}>
        <WebSocketProvider>
          <RouterProvider router={router} />
          <Toaster 
            position="top-center" 
            richColors 
            expand={true}
            duration={4000}
          />
        </WebSocketProvider>
      </QueryClientProvider>
    </LanguageProvider>
  </React.StrictMode>
);
