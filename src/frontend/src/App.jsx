import React, { useState, useEffect } from 'react';
import { Routes, Route, Navigate, useNavigate, useLocation } from 'react-router-dom';
import { LogOut, Disc3 } from 'lucide-react';
import ChatInterface from './components/ChatInterface';
import LoginScreen from './components/LoginScreen';
import Sidebar from './components/Sidebar';
import './index.css';

function App() {
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [isCheckingAuth, setIsCheckingAuth] = useState(true);
  const [isProcessing, setIsProcessing] = useState(false);
  const navigate = useNavigate();
  const location = useLocation();

  useEffect(() => {
    const checkAuthStatus = async () => {
      // 1. Check if we just returned from Spotify Auth success
      const urlParams = new URLSearchParams(window.location.search);
      const authStatus = urlParams.get('auth');

      if (authStatus === 'success') {
        setIsAuthenticated(true);
        // Clean up the URL without triggering a reload
        window.history.replaceState({}, document.title, window.location.pathname);
        
        // Generate a unique ID for the chat session and navigate there
        // Instead of generating an ID here, we just go to the new chat home page
        navigate(`/chat`, { replace: true });
        setIsCheckingAuth(false);
        return;
      }

      // 2. If not just returning from auth, check the backend to see if we have a valid cookie
      try {
        const response = await fetch("/api/auth/status", {
            credentials: "include" 
        });
        const data = await response.json();
        
        if (data.authenticated) {
            setIsAuthenticated(true);
            // If they are authenticated but sitting on the root page, redirect to the chat home
            if (window.location.pathname === '/') {
                navigate(`/chat`, { replace: true });
            }
        } else {
            setIsAuthenticated(false);
        }
      } catch (err) {
        console.error("Failed to check auth status:", err);
        setIsAuthenticated(false);
      } finally {
        setIsCheckingAuth(false);
      }
    };

    checkAuthStatus();
  }, [navigate]);

  if (isCheckingAuth) {
      return (
          <div className="h-screen w-screen bg-spotify-darkest flex items-center justify-center">
              <Disc3 className="w-10 h-10 text-spotify-green animate-[spin_2s_linear_infinite]" />
          </div>
      );
  }

  return (
    <div className="h-screen w-screen bg-spotify-darkest text-zinc-300 flex flex-col font-sans overflow-hidden">
      {/* Header */}
      <header className="absolute top-0 w-full z-10 flex items-center justify-between px-6 py-4 bg-spotify-darkest/70 backdrop-blur-md border-b border-white/5">
        <div className="flex items-center space-x-3">
          <div className="w-8 h-8 rounded-full bg-spotify-green flex items-center justify-center text-black shadow-lg shadow-spotify-green/20">
            <Disc3 className="w-5 h-5 animate-[spin_4s_linear_infinite]" />
          </div>
          <h1 
            className="text-xl font-bold tracking-tight text-white hover:text-spotify-green transition-colors cursor-pointer"
            onClick={() => navigate('/chat')}
          >
            Timbre
          </h1>
        </div>
        {isAuthenticated && (
          <button
            onClick={async () => {
              try {
                await fetch("/api/auth/logout", { 
                    method: "POST",
                    credentials: "include" 
                });
              } catch (e) {
                console.error("Logout error", e);
              }
              setIsAuthenticated(false);
              navigate('/');
            }}
            className="flex items-center space-x-2 text-sm text-zinc-400 hover:text-white transition-colors px-3 py-1.5 rounded-full hover:bg-white/5"
          >
            <LogOut className="w-4 h-4" />
            <span>Sign Out</span>
          </button>
        )}
      </header>

      {/* Main Content Area */}
      <main className="flex-1 flex flex-row overflow-hidden relative pt-[73px]">
        {isAuthenticated && <Sidebar isProcessing={isProcessing} />}
        <div className="flex-1 flex flex-col h-full overflow-hidden relative">
          <Routes>
            <Route path="/" element={
              isAuthenticated ? <Navigate to={`/chat`} replace /> : <LoginScreen />
            } />
            
            <Route path="/chat" element={
              isAuthenticated ? <ChatInterface key="chat-home" onProcessingChange={setIsProcessing} /> : <Navigate to="/" replace />
            } />

            <Route path="/chat/:chatId" element={
              isAuthenticated ? <ChatInterface key={location.pathname} onProcessingChange={setIsProcessing} /> : <Navigate to="/" replace />
            } />
            
            {/* Catch-all redirect */}
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </div>
      </main>
    </div>
  );
}

export default App;