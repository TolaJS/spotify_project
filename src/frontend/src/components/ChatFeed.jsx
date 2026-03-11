import React from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Music } from 'lucide-react';
import MessageBubble from './MessageBubble';

function ChatFeed({ messages }) {
    if (messages.length === 0) {
        return (
            <motion.div 
                initial={{ opacity: 0, scale: 0.95 }}
                animate={{ opacity: 1, scale: 1 }}
                transition={{ duration: 0.5 }}
                className="h-full flex flex-col items-center justify-center text-center opacity-60"
            >
                <div className="w-16 h-16 bg-zinc-800 rounded-full mb-6 flex items-center justify-center shadow-lg border border-white/5">
                    <Music className="w-8 h-8 text-spotify-green" />
                </div>
                <h2 className="text-2xl font-bold text-white mb-3">How can I help you today?</h2>
                <p className="text-sm text-zinc-400 max-w-sm leading-relaxed">
                    Try asking me to queue a song, create a playlist based on your recent listening,
                    or search for your favorite artists.
                </p>
            </motion.div>
        );
    }

    return (
        <div className="flex flex-col space-y-2 pb-2">
            <AnimatePresence mode="popLayout">
                {messages.map((msg, idx) => (
                    <MessageBubble key={msg.id || idx} message={msg} />
                ))}
            </AnimatePresence>
        </div>
    );
}

export default ChatFeed;