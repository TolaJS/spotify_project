import React, { useState, useEffect } from 'react';
import { Routes, Route, Navigate, useNavigate, useLocation } from 'react-router-dom';
import { LogOut, Disc3, Menu, LogIn } from 'lucide-react';
import ChatInterface from './components/ChatInterface';
import LoginScreen from './components/LoginScreen';
import Sidebar from './components/Sidebar';
import TutorialModal from './components/TutorialModal';
import './index.css';

function App() {
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [userId, setUserId] = useState(null);
  const [isCheckingAuth, setIsCheckingAuth] = useState(true);
  const [isProcessing, setIsProcessing] = useState(false);
  const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false);
  const [showTutorial, setShowTutorial] = useState(false);
  const navigate = useNavigate();
  const location = useLocation();

  useEffect(() => {
    const checkAuthStatus = async () => {
      // 1. If returning from Spotify OAuth, clean up the URL before the auth status check below.
      const urlParams = new URLSearchParams(window.location.search);
      if (urlParams.get('auth') === 'success') {
        window.history.replaceState({}, document.title, window.location.pathname);
      }

      // 2. Always check the backend to confirm auth and get the user ID.
      //    This also covers the OAuth redirect case — we need the user_id for WebSocket handshakes.
      try {
        const response = await fetch("/api/auth/status", {
            credentials: "include"
        });
        const data = await response.json();

        if (data.authenticated) {
            setIsAuthenticated(true);
            setUserId(data.user_id);
            if (!localStorage.getItem('tutorialSeen')) {
                setShowTutorial(true);
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
  }, []); // Run once on mount only

  if (isCheckingAuth) {
      return (
          <div className="h-screen w-screen bg-spotify-darkest flex items-center justify-center">
              <Disc3 className="w-10 h-10 text-spotify-green animate-[spin_2s_linear_infinite]" />
          </div>
      );
  }

  return (
    <div className="h-[100dvh] w-screen bg-spotify-darkest text-zinc-300 flex flex-col font-sans overflow-hidden">
      {/* Header */}
      <header className="absolute top-0 w-full z-10 flex items-center justify-between px-6 py-4 bg-spotify-darkest/70 backdrop-blur-md border-b border-white/5">
        <div className="flex items-center space-x-3">
          {isAuthenticated && (
            <button
              onClick={() => setIsMobileMenuOpen(true)}
              className="md:hidden p-2 rounded-xl hover:bg-white/5 text-zinc-400 hover:text-white transition-colors"
            >
              <Menu className="w-5 h-5" />
            </button>
          )}
          <div className="w-8 h-8 rounded-full bg-spotify-green flex items-center justify-center text-black shadow-lg shadow-spotify-green/20">
            <Disc3 className="w-5 h-5 animate-[spin_4s_linear_infinite]" />
          </div>
          <h1
            className="text-xl font-bold tracking-tight text-white hover:text-spotify-green transition-colors cursor-pointer"
            onClick={() => navigate('/app')}
          >
            Timber
          </h1>
        </div>
        {!isAuthenticated && (
          <button
            onClick={async () => {
              try {
                const res = await fetch("/api/auth/url");
                const { auth_url } = await res.json();
                window.location.href = auth_url;
              } catch (e) {
                console.error("Login error", e);
              }
            }}
            className="md:hidden flex items-center space-x-2 text-sm font-bold text-black bg-spotify-green hover:bg-[#1ed760] transition-colors px-4 py-1.5 rounded-full"
          >
            <LogIn className="w-4 h-4" />
            <span>Log In</span>
          </button>
        )}
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
        {isAuthenticated && (
          <Sidebar
            isProcessing={isProcessing}
            isMobileOpen={isMobileMenuOpen}
            onMobileClose={() => setIsMobileMenuOpen(false)}
            onShowTutorial={() => setShowTutorial(true)}
          />
        )}
        <div className="flex-1 flex flex-col h-full overflow-hidden relative">
          <Routes>
            <Route path="/" element={
              isAuthenticated ? <Navigate to={`/app`} replace /> : <LoginScreen />
            } />
            
            <Route path="/app" element={
              isAuthenticated ? <ChatInterface key="chat-home" userId={userId} onProcessingChange={setIsProcessing} /> : <Navigate to="/" replace />
            } />

            <Route path="/app/:chatId" element={
              isAuthenticated ? <ChatInterface key={location.pathname} userId={userId} onProcessingChange={setIsProcessing} /> : <Navigate to="/" replace />
            } />
            
            {/* Catch-all redirect */}
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </div>
      </main>

      <TutorialModal isOpen={showTutorial} onClose={() => setShowTutorial(false)} />
    </div>
  );
}

export default App;