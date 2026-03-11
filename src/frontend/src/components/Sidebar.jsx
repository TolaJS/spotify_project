import React, { useState } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { Menu, Plus, MessageSquare, UploadCloud, ChevronLeft, ChevronRight } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import UploadModal from './UploadModal';

function Sidebar({ isProcessing }) {
    const [isExpanded, setIsExpanded] = useState(false);
    const [isUploadModalOpen, setIsUploadModalOpen] = useState(false);
    const [isLoadingPrevious, setIsLoadingPrevious] = useState(false);
    const navigate = useNavigate();
    const location = useLocation();

    // Parse the chatId the user is currently viewing from the URL
    const currentChatId = location.pathname.startsWith('/chat/')
        ? location.pathname.slice('/chat/'.length)
        : null;

    // The session the user is actively conversing with (set in localStorage on message send)
    const activeSessionId = localStorage.getItem('activeSessionId');

    // True when the user is browsing a previous session, not their active one
    const isViewingPrevious = !!(currentChatId && activeSessionId && currentChatId !== activeSessionId);

    const handleNewChat = () => {
        navigate(`/chat`);
    };

    const handlePreviousChat = async () => {
        setIsLoadingPrevious(true);
        try {
            // Exclude the session the user is currently on so "Previous Chat"
            // always navigates to a genuinely different session.
            const excludeParam = currentChatId ? `?exclude_id=${currentChatId}` : '';
            const response = await fetch(`/api/chats/latest${excludeParam}`, {
                credentials: "include"
            });
            if (response.ok) {
                const data = await response.json();
                if (data.session_id) {
                    navigate(`/chat/${data.session_id}`);
                } else {
                    alert("No previous chat found.");
                }
            }
        } catch (error) {
            console.error("Failed to load previous chat", error);
        } finally {
            setIsLoadingPrevious(false);
        }
    };

    const handleReturnToCurrent = () => {
        if (activeSessionId) {
            navigate(`/chat/${activeSessionId}`);
        }
    };

    return (
        <>
            <motion.div 
                animate={{ width: isExpanded ? 260 : 72 }}
                transition={{ duration: 0.3, ease: "easeInOut" }}
                className="h-full bg-zinc-900/50 border-r border-white/5 flex flex-col shrink-0 relative hidden md:flex backdrop-blur-md z-20"
            >
                {/* Toggle Button */}
                <div className="pt-4 pb-2 px-4 flex items-center justify-start shrink-0">
                    <button 
                        onClick={() => setIsExpanded(!isExpanded)}
                        className="p-2 rounded-xl hover:bg-white/5 text-zinc-400 hover:text-white transition-colors flex items-center justify-center ml-[2px]"
                    >
                        <Menu className="w-5 h-5" />
                    </button>
                </div>

                {/* Actions */}
                <div className="flex-1 flex flex-col gap-2 px-3 overflow-hidden mt-2">
                    <div className="flex-1 flex flex-col gap-2">
                        {/* New Chat Button */}
                        <button 
                            onClick={handleNewChat}
                            className="flex items-center p-3 rounded-xl hover:bg-white/5 text-zinc-300 hover:text-white transition-colors group w-full h-[48px] relative overflow-hidden"
                            title={!isExpanded ? "New Chat" : ""}
                        >
                            <div className="flex items-center justify-center shrink-0 w-6 h-6">
                                <Plus className="w-5 h-5" />
                            </div>
                            <AnimatePresence>
                                {isExpanded && (
                                    <motion.span 
                                        initial={{ opacity: 0 }}
                                        animate={{ opacity: 1 }}
                                        exit={{ opacity: 0 }}
                                        transition={{ duration: 0.2 }}
                                        className="absolute left-12 font-medium whitespace-nowrap"
                                    >
                                        New Chat
                                    </motion.span>
                                )}
                            </AnimatePresence>
                        </button>

                        {/* Previous Chat Button */}
                        <button
                            onClick={handlePreviousChat}
                            disabled={isLoadingPrevious || isProcessing}
                            className="flex items-center p-3 rounded-xl hover:bg-white/5 text-zinc-300 hover:text-white transition-colors group w-full h-[48px] relative overflow-hidden disabled:opacity-50"
                            title={isProcessing ? "Wait for the response to finish" : (!isExpanded ? "Previous Chat" : "")}
                        >
                            <div className="flex items-center justify-center shrink-0 w-6 h-6">
                                <MessageSquare className="w-5 h-5 text-zinc-400 group-hover:text-white transition-colors" />
                            </div>
                            <AnimatePresence>
                                {isExpanded && (
                                    <motion.span
                                        initial={{ opacity: 0 }}
                                        animate={{ opacity: 1 }}
                                        exit={{ opacity: 0 }}
                                        transition={{ duration: 0.2 }}
                                        className="absolute left-12 text-sm whitespace-nowrap"
                                    >
                                        Previous Chat
                                    </motion.span>
                                )}
                            </AnimatePresence>
                        </button>

                        {/* Return to Current Chat — only shown when browsing a previous session */}
                        {isViewingPrevious && (
                            <button
                                onClick={handleReturnToCurrent}
                                className="flex items-center p-3 rounded-xl hover:bg-spotify-green/10 text-spotify-green transition-colors group w-full h-[48px] relative overflow-hidden"
                                title={!isExpanded ? "Return to current chat" : ""}
                            >
                                <div className="flex items-center justify-center shrink-0 w-6 h-6">
                                    <ChevronRight className="w-5 h-5" />
                                </div>
                                <AnimatePresence>
                                    {isExpanded && (
                                        <motion.span
                                            initial={{ opacity: 0 }}
                                            animate={{ opacity: 1 }}
                                            exit={{ opacity: 0 }}
                                            transition={{ duration: 0.2 }}
                                            className="absolute left-12 text-sm font-medium whitespace-nowrap"
                                        >
                                            Return to current
                                        </motion.span>
                                    )}
                                </AnimatePresence>
                            </button>
                        )}
                    </div>

                    {/* Bottom Section */}
                    <div className="pb-4 flex flex-col gap-2">
                        <div className="my-1 border-t border-white/5 mx-2"></div>
                        
                        {/* Upload History Button */}
                        <button 
                            onClick={() => setIsUploadModalOpen(true)}
                            className="flex items-center p-3 rounded-xl hover:bg-spotify-green/10 text-spotify-green transition-colors group w-full h-[48px] relative overflow-hidden"
                            title={!isExpanded ? "Upload History" : ""}
                        >
                            <div className="flex items-center justify-center shrink-0 w-6 h-6">
                                <UploadCloud className="w-5 h-5" />
                            </div>
                            <AnimatePresence>
                                {isExpanded && (
                                    <motion.span 
                                        initial={{ opacity: 0 }}
                                        animate={{ opacity: 1 }}
                                        exit={{ opacity: 0 }}
                                        transition={{ duration: 0.2 }}
                                        className="absolute left-12 text-sm font-medium whitespace-nowrap"
                                    >
                                        Upload History
                                    </motion.span>
                                )}
                            </AnimatePresence>
                        </button>
                    </div>
                </div>
            </motion.div>

            {/* Upload Modal Overlay */}
            <UploadModal isOpen={isUploadModalOpen} onClose={() => setIsUploadModalOpen(false)} />
        </>
    );
}

export default Sidebar;