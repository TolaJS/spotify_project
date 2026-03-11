import React from 'react';
import { LogIn, Disc3, Sparkles, Database } from 'lucide-react';

function LoginScreen() {
    const handleLogin = async () => {
        try {
            const response = await fetch("/api/auth/url");
            if (!response.ok) throw new Error("Failed to fetch auth URL");
            const { auth_url } = await response.json();
            window.location.href = auth_url;
        } catch (err) {
            console.error("Login error:", err);
        }
    };

    return (
        <div className="flex w-full h-full bg-spotify-darkest relative overflow-hidden flex-col md:flex-row">
            {/* Background decorative elements */}
            <div className="absolute top-[-10%] left-[-10%] w-96 h-96 bg-spotify-green/10 rounded-full blur-[120px] pointer-events-none z-0"></div>
            <div className="absolute bottom-[-10%] right-[-10%] w-96 h-96 bg-blue-500/10 rounded-full blur-[120px] pointer-events-none z-0"></div>

            {/* Left Side: About Section (75%) */}
            <div className="w-full md:w-3/4 h-full p-10 md:p-16 lg:p-24 overflow-y-auto z-10 custom-scrollbar flex flex-col justify-center">
                <div className="max-w-4xl">
                    <h1 className="text-5xl md:text-7xl font-extrabold text-white mb-6 tracking-tight leading-tight">
                        Your music,<br/><span className="text-transparent bg-clip-text bg-gradient-to-r from-spotify-green to-blue-400">conversationalized.</span>
                    </h1>
                    
                    <p className="text-xl md:text-2xl text-zinc-300 mb-12 leading-relaxed max-w-3xl">
                        Spotify AI Assistant is a next-generation exploration tool. Use natural language to dig deep into your listening history, discover hidden connections between artists, and queue up the perfect vibe.
                    </p>

                    <div className="grid grid-cols-1 md:grid-cols-2 gap-8 mt-12">
                        <div className="bg-zinc-800/40 border border-white/5 p-8 rounded-3xl backdrop-blur-sm transition-transform hover:scale-[1.02]">
                            <div className="w-14 h-14 bg-zinc-800 rounded-2xl flex items-center justify-center mb-6 text-spotify-green shadow-lg">
                                <Sparkles className="w-7 h-7" />
                            </div>
                            <h3 className="text-2xl font-bold text-white mb-3">Smart Playlists</h3>
                            <p className="text-zinc-400 leading-relaxed text-lg">Ask the AI to generate a mix of "upbeat indie rock from 2010" and watch it instantly queue up on your account.</p>
                        </div>
                        
                        <div className="bg-zinc-800/40 border border-white/5 p-8 rounded-3xl backdrop-blur-sm transition-transform hover:scale-[1.02]">
                            <div className="w-14 h-14 bg-zinc-800 rounded-2xl flex items-center justify-center mb-6 text-blue-400 shadow-lg">
                                <Database className="w-7 h-7" />
                            </div>
                            <h3 className="text-2xl font-bold text-white mb-3">Knowledge Graph</h3>
                            <p className="text-zinc-400 leading-relaxed text-lg">Powered by Graph RAG technology, the assistant understands deep relationships between tracks, genres, and producers.</p>
                        </div>
                    </div>
                </div>
            </div>

            {/* Right Side: Login Portal (25%) */}
            <div className="w-full md:w-1/4 h-full bg-zinc-900/60 backdrop-blur-xl border-l border-white/5 flex flex-col justify-center items-center p-8 z-10 shadow-2xl">
                <div className="w-full max-w-sm text-center">
                    <div className="w-24 h-24 bg-spotify-green rounded-full mx-auto mb-8 flex items-center justify-center shadow-[0_0_30px_rgba(29,185,84,0.3)]">
                        <Disc3 className="w-12 h-12 text-black animate-[spin_4s_linear_infinite]" />
                    </div>
                    
                    <h2 className="text-3xl font-extrabold text-white mb-3 tracking-tight">Ready to dive in?</h2>
                    <p className="text-zinc-400 mb-10 text-base leading-relaxed">
                        Link your Spotify account to unlock all AI features and personalized insights.
                    </p>

                    <button
                        onClick={handleLogin}
                        className="w-full flex items-center justify-center space-x-3 bg-spotify-green hover:bg-[#1ed760] text-black font-bold py-4 px-6 rounded-full transition-all duration-300 transform hover:scale-[1.02] active:scale-95 shadow-[0_0_15px_rgba(29,185,84,0.3)] focus:outline-none focus:ring-4 focus:ring-spotify-green focus:ring-opacity-50"
                    >
                        <LogIn className="w-6 h-6" />
                        <span>LOG IN WITH SPOTIFY</span>
                    </button>
                    
                    <p className="mt-8 text-sm text-zinc-500 font-medium">
                        We never store your personal data.
                    </p>
                </div>
            </div>
        </div>
    );
}

export default LoginScreen;