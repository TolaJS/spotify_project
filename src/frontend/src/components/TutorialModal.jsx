import React, { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { X, ChevronRight, ChevronLeft, Upload, MessageSquare, Sparkles, Trash2, ExternalLink, History, RefreshCw } from 'lucide-react';

const STEPS = [
    {
        icon: <History className="w-8 h-8 text-spotify-green" />,
        title: "Request your Spotify history",
        content: (
            <div className="space-y-3 text-zinc-400 text-sm leading-relaxed">
                <p>
                    Timber works best with your full listening history. To get it, request your
                    <strong className="text-white"> Extended Streaming History</strong> from Spotify — this covers everything you've ever played.
                </p>
                <ol className="list-decimal list-inside space-y-1.5 text-zinc-400">
                    <li>Go to <strong className="text-white">Spotify Account → Privacy Settings</strong></li>
                    <li>Scroll to <strong className="text-white">"Download your data"</strong></li>
                    <li>Select <strong className="text-white">Extended Streaming History only</strong> — uncheck all other options</li>
                    <li>Click <strong className="text-white">Request data</strong></li>
                </ol>
                <p className="text-zinc-500 text-xs">
                    Spotify can take up to 30 days to send the files. You'll get an email when they're ready.
                </p>
                <a
                    href="https://www.spotify.com/account/privacy/"
                    target="_blank"
                    rel="noopener noreferrer"
                    className="inline-flex items-center gap-1.5 text-spotify-green hover:underline text-sm mt-1"
                >
                    Open Spotify Privacy Settings <ExternalLink className="w-3.5 h-3.5" />
                </a>
            </div>
        ),
    },
    {
        icon: <Upload className="w-8 h-8 text-spotify-green" />,
        title: "Upload your history",
        content: (
            <div className="space-y-3 text-zinc-400 text-sm leading-relaxed">
                <p>
                    Once Spotify sends your files, upload them to Timber so the AI can analyse your listening patterns.
                </p>
                <ol className="list-decimal list-inside space-y-1.5">
                    <li>Click the <strong className="text-white">Upload History</strong> button at the bottom of the left sidebar</li>
                    <li>Select all the <strong className="text-white">Streaming_History_Audio_*.json</strong> files from your Spotify data package</li>
                    <li>Timber will process them in the background — you'll get a notification when it's done</li>
                </ol>
                <p className="text-zinc-500 text-xs">
                    You can upload multiple files at once. Large histories may take a few minutes to process.
                </p>
            </div>
        ),
    },
    {
        icon: <RefreshCw className="w-8 h-8 text-spotify-green" />,
        title: "Auto-sync your history",
        content: (
            <div className="space-y-3 text-zinc-400 text-sm leading-relaxed">
                <p>
                    Timber can automatically keep your listening history up to date without you having to upload files manually.
                </p>
                <ul className="space-y-2">
                    <li className="flex items-start gap-2">
                        <ChevronRight className="w-4 h-4 text-spotify-green shrink-0 mt-0.5" />
                        <span>Open <strong className="text-white">Settings</strong> in the sidebar and enable <strong className="text-white">Auto-sync history</strong></span>
                    </li>
                    <li className="flex items-start gap-2">
                        <ChevronRight className="w-4 h-4 text-spotify-green shrink-0 mt-0.5" />
                        <span>Timber will periodically fetch your recently played tracks from Spotify and add them to your history</span>
                    </li>
                    <li className="flex items-start gap-2">
                        <ChevronRight className="w-4 h-4 text-spotify-green shrink-0 mt-0.5" />
                        <span>This works alongside your uploaded history — both sources are combined</span>
                    </li>
                </ul>
                <p className="text-zinc-500 text-xs">
                    Note: auto-sync only covers recent plays. For your full listening history, upload your Extended Streaming History files.
                </p>
            </div>
        ),
    },
    {
        icon: <MessageSquare className="w-8 h-8 text-spotify-green" />,
        title: "Start a chat",
        content: (
            <div className="space-y-3 text-zinc-400 text-sm leading-relaxed">
                <p>
                    Type any message in the input box to start a new conversation with Timber.
                </p>
                <ul className="space-y-2">
                    <li className="flex items-start gap-2">
                        <ChevronRight className="w-4 h-4 text-spotify-green shrink-0 mt-0.5" />
                        <span>Click <strong className="text-white">New Chat</strong> in the sidebar to start a fresh conversation at any time</span>
                    </li>
                    <li className="flex items-start gap-2">
                        <ChevronRight className="w-4 h-4 text-spotify-green shrink-0 mt-0.5" />
                        <span>Click <strong className="text-white">Previous Chat</strong> to pick up where you left off in your last session</span>
                    </li>
                    <li className="flex items-start gap-2">
                        <ChevronRight className="w-4 h-4 text-spotify-green shrink-0 mt-0.5" />
                        <span>On mobile, tap the <strong className="text-white">menu icon</strong> in the top-left to access the sidebar</span>
                    </li>
                </ul>
            </div>
        ),
    },
    {
        icon: <Sparkles className="w-8 h-8 text-spotify-green" />,
        title: "What to ask",
        content: (
            <div className="space-y-3 text-zinc-400 text-sm leading-relaxed">
                <p>Timber can help with playback, history analysis, and music discovery. Try asking:</p>
                <div className="grid grid-cols-1 gap-2">
                    {[
                        "Play some upbeat indie rock",
                        "What were my top artists last year?",
                        "Queue 10 songs that sound like a rainy day",
                        "How many times have I played Frank Ocean?",
                        "Create a playlist of my most played songs",
                        "What did I listen to most this summer?",
                    ].map((q, i) => (
                        <div key={i} className="bg-zinc-800/60 border border-white/5 rounded-lg px-3 py-2 text-zinc-300 text-xs">
                            "{q}"
                        </div>
                    ))}
                </div>
            </div>
        ),
    },
    {
        icon: <Trash2 className="w-8 h-8 text-red-400" />,
        title: "Managing your data",
        content: (
            <div className="space-y-3 text-zinc-400 text-sm leading-relaxed">
                <p>
                    You're in full control of your data. To delete everything Timber has stored:
                </p>
                <ol className="list-decimal list-inside space-y-1.5">
                    <li>Click the <strong className="text-white">Settings</strong> icon at the bottom of the sidebar</li>
                    <li>Select <strong className="text-white">Delete my data</strong></li>
                    <li>Confirm the deletion</li>
                </ol>
                <p className="text-zinc-500 text-xs">
                    This permanently removes your listening history, chat sessions, and account data. It cannot be undone.
                </p>
            </div>
        ),
    },
];

function TutorialModal({ isOpen, onClose }) {
    const [step, setStep] = useState(0);
    const isFirst = step === 0;
    const isLast = step === STEPS.length - 1;

    const handleClose = () => {
        localStorage.setItem('tutorialSeen', 'true');
        onClose();
    };

    const handleNext = () => {
        if (isLast) {
            handleClose();
        } else {
            setStep(s => s + 1);
        }
    };

    return (
        <AnimatePresence>
            {isOpen && (
                <>
                    {/* Backdrop */}
                    <motion.div
                        initial={{ opacity: 0 }}
                        animate={{ opacity: 1 }}
                        exit={{ opacity: 0 }}
                        className="fixed inset-0 bg-black/70 z-50 backdrop-blur-sm"
                        onClick={handleClose}
                    />

                    {/* Modal */}
                    <motion.div
                        initial={{ opacity: 0, scale: 0.95, y: 10 }}
                        animate={{ opacity: 1, scale: 1, y: 0 }}
                        exit={{ opacity: 0, scale: 0.95, y: 10 }}
                        transition={{ duration: 0.2 }}
                        className="fixed inset-0 z-50 flex items-center justify-center p-4 pointer-events-none"
                    >
                        <div
                            className="bg-zinc-900 border border-white/10 rounded-2xl shadow-2xl w-full max-w-lg pointer-events-auto flex flex-col"
                            onClick={e => e.stopPropagation()}
                        >
                            {/* Header */}
                            <div className="flex items-center justify-between px-6 pt-6 pb-4 border-b border-white/5">
                                <div className="flex items-center gap-3">
                                    {STEPS[step].icon}
                                    <h2 className="text-lg font-bold text-white">{STEPS[step].title}</h2>
                                </div>
                                <button
                                    onClick={handleClose}
                                    className="text-zinc-500 hover:text-white transition-colors p-1 rounded-lg hover:bg-white/5"
                                >
                                    <X className="w-5 h-5" />
                                </button>
                            </div>

                            {/* Content */}
                            <div className="px-6 py-5 flex-1 overflow-y-auto max-h-80 custom-scrollbar">
                                <AnimatePresence mode="wait">
                                    <motion.div
                                        key={step}
                                        initial={{ opacity: 0, x: 10 }}
                                        animate={{ opacity: 1, x: 0 }}
                                        exit={{ opacity: 0, x: -10 }}
                                        transition={{ duration: 0.15 }}
                                    >
                                        {STEPS[step].content}
                                    </motion.div>
                                </AnimatePresence>
                            </div>

                            {/* Footer */}
                            <div className="px-6 pb-6 pt-4 border-t border-white/5 flex items-center justify-between">
                                {/* Step dots */}
                                <div className="flex items-center gap-1.5">
                                    {STEPS.map((_, i) => (
                                        <button
                                            key={i}
                                            onClick={() => setStep(i)}
                                            className={`rounded-full transition-all ${
                                                i === step
                                                    ? 'w-4 h-2 bg-spotify-green'
                                                    : 'w-2 h-2 bg-zinc-600 hover:bg-zinc-400'
                                            }`}
                                        />
                                    ))}
                                </div>

                                {/* Navigation */}
                                <div className="flex items-center gap-2">
                                    <button
                                        onClick={handleClose}
                                        className="text-sm text-zinc-500 hover:text-white transition-colors px-3 py-1.5"
                                    >
                                        Skip
                                    </button>
                                    {!isFirst && (
                                        <button
                                            onClick={() => setStep(s => s - 1)}
                                            className="flex items-center gap-1 text-sm text-zinc-300 hover:text-white bg-white/5 hover:bg-white/10 px-3 py-1.5 rounded-lg transition-colors"
                                        >
                                            <ChevronLeft className="w-4 h-4" />
                                            Back
                                        </button>
                                    )}
                                    <button
                                        onClick={handleNext}
                                        className="flex items-center gap-1 text-sm font-semibold text-black bg-spotify-green hover:bg-[#1ed760] px-4 py-1.5 rounded-lg transition-colors"
                                    >
                                        {isLast ? 'Get Started' : 'Next'}
                                        {!isLast && <ChevronRight className="w-4 h-4" />}
                                    </button>
                                </div>
                            </div>
                        </div>
                    </motion.div>
                </>
            )}
        </AnimatePresence>
    );
}

export default TutorialModal;
