import React from 'react';
import { LogIn, Disc3, Sparkles, History } from 'lucide-react';

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
        // Container: scrollable so mobile can reach all content; flex-col on mobile, flex-row on desktop
        <div className="flex w-full h-full bg-spotify-darkest relative overflow-y-auto overflow-x-hidden flex-col md:flex-row">
            {/* Background decorative elements */}
            <div className="absolute top-[-10%] left-[-10%] w-96 h-96 bg-spotify-green/10 rounded-full blur-[120px] pointer-events-none z-0"></div>
            <div className="absolute bottom-[-10%] right-[-10%] w-96 h-96 bg-blue-500/10 rounded-full blur-[120px] pointer-events-none z-0"></div>

            {/* Right Side: Login Portal — bottom on mobile, right column on desktop */}
            <div className="order-last md:order-last w-full md:w-1/4 md:h-full bg-zinc-900/60 backdrop-blur-xl border-t md:border-t-0 md:border-l border-white/5 flex flex-col justify-center items-center py-10 px-8 z-10 shadow-2xl shrink-0">
                <div className="w-full max-w-sm text-center">
                    <div className="w-20 h-20 md:w-24 md:h-24 bg-spotify-green rounded-full mx-auto mb-6 md:mb-8 flex items-center justify-center shadow-[0_0_30px_rgba(29,185,84,0.3)]">
                        <Disc3 className="w-10 h-10 md:w-12 md:h-12 text-black animate-[spin_4s_linear_infinite]" />
                    </div>

                    <h2 className="text-2xl md:text-3xl font-extrabold text-white mb-3 tracking-tight">Ready to dive in?</h2>
                    <p className="text-zinc-400 mb-8 text-base leading-relaxed">
                        Link your Spotify account to start chatting with your personal music AI.
                    </p>

                    <button
                        onClick={handleLogin}
                        className="w-full flex items-center justify-center space-x-3 bg-spotify-green hover:bg-[#1ed760] text-black font-bold py-4 px-6 rounded-full transition-all duration-300 transform hover:scale-[1.02] active:scale-95 shadow-[0_0_15px_rgba(29,185,84,0.3)] focus:outline-none focus:ring-4 focus:ring-spotify-green focus:ring-opacity-50"
                    >
                        <LogIn className="w-6 h-6" />
                        <span>LOG IN WITH SPOTIFY</span>
                    </button>

                </div>
            </div>

            {/* Left Side: About Section */}
            <div className="order-first md:order-first w-full md:w-3/4 md:h-full p-8 md:p-16 lg:p-24 md:overflow-y-auto z-10 flex flex-col justify-center custom-scrollbar">
                <div className="max-w-4xl">
                    <h1 className="text-4xl md:text-7xl font-extrabold text-white mb-5 md:mb-6 tracking-tight leading-tight">
                        Your music,<br/><span className="text-transparent bg-clip-text bg-gradient-to-r from-spotify-green to-blue-400">on demand.</span>
                    </h1>

                    <p className="text-lg md:text-2xl text-zinc-300 mb-8 md:mb-12 leading-relaxed max-w-3xl">
                        Timber is your personal Spotify AI. Control playback, build playlists, and dig into your full listening history — all through natural conversation.
                    </p>

                    <div className="grid grid-cols-1 md:grid-cols-2 gap-5 md:gap-8 mt-4 md:mt-12">
                        <div className="bg-zinc-800/40 border border-white/5 p-6 md:p-8 rounded-3xl backdrop-blur-sm transition-transform hover:scale-[1.02]">
                            <div className="w-12 h-12 md:w-14 md:h-14 bg-zinc-800 rounded-2xl flex items-center justify-center mb-4 md:mb-6 text-spotify-green shadow-lg">
                                <Sparkles className="w-6 h-6 md:w-7 md:h-7" />
                            </div>
                            <h3 className="text-xl md:text-2xl font-bold text-white mb-2 md:mb-3">Playback Control</h3>
                            <p className="text-zinc-400 leading-relaxed md:text-lg">Play, pause, skip, queue songs, and build playlists — just by asking. Timber searches and acts on Spotify instantly.</p>
                        </div>

                        <div className="bg-zinc-800/40 border border-white/5 p-6 md:p-8 rounded-3xl backdrop-blur-sm transition-transform hover:scale-[1.02]">
                            <div className="w-12 h-12 md:w-14 md:h-14 bg-zinc-800 rounded-2xl flex items-center justify-center mb-4 md:mb-6 text-blue-400 shadow-lg">
                                <History className="w-6 h-6 md:w-7 md:h-7" />
                            </div>
                            <h3 className="text-xl md:text-2xl font-bold text-white mb-2 md:mb-3">Listening History</h3>
                            <p className="text-zinc-400 leading-relaxed md:text-lg">Upload your Spotify Extended Streaming History and ask anything — top artists by year, your most-played genres, and more.</p>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    );
}

export default LoginScreen;
