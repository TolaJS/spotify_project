import React, { useState, useEffect, useRef } from 'react';
import { createPortal } from 'react-dom';
import { useNavigate, useLocation } from 'react-router-dom';
import { Menu, Plus, MessageSquare, UploadCloud, ChevronRight, Settings, Trash2, AlertTriangle, RefreshCw, BookOpen } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import UploadModal from './UploadModal';
import Toast from './Toast';
import { useUploadJob } from '../hooks/useUploadJob';

function Sidebar({ isProcessing, isMobileOpen, onMobileClose, onShowTutorial }) {
    const [isExpanded, setIsExpanded] = useState(false);
    const [isUploadModalOpen, setIsUploadModalOpen] = useState(false);
    const [isLoadingPrevious, setIsLoadingPrevious] = useState(false);
    const [toast, setToast] = useState(null);
    const [isSettingsOpen, setIsSettingsOpen] = useState(false);
    const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);
    const [isDeleting, setIsDeleting] = useState(false);
    const [autoSync, setAutoSync] = useState(false);
    const [isTogglingSync, setIsTogglingSync] = useState(false);
    const [dropdownPos, setDropdownPos] = useState({ bottom: 0, left: 0 });
    const settingsBtnRef = useRef(null);
    const dropdownRef = useRef(null);

    const { status, progress, message, totalEvents, startJob, resetJob } = useUploadJob();
    const prevStatusRef = useRef(status);
    const navigate = useNavigate();
    const location = useLocation();

    // Parse the chatId the user is currently viewing from the URL
    const currentChatId = location.pathname.startsWith('/app/')
        ? location.pathname.slice('/app/'.length)
        : null;

    // The session the user is actively conversing with (set in localStorage on message send)
    const activeSessionId = localStorage.getItem('activeSessionId');

    // True when the user is browsing a previous session, not their active one
    const isViewingPrevious = !!(currentChatId && activeSessionId && currentChatId !== activeSessionId);

    // Fire a toast when ingestion completes or errors, but only if modal is closed
    useEffect(() => {
        const prev = prevStatusRef.current;
        prevStatusRef.current = status;

        if (prev !== 'processing') return;

        if (status === 'complete' && !isUploadModalOpen) {
            setToast({
                type: 'success',
                message: `Ingestion complete! ${totalEvents?.toLocaleString() ?? ''} listening events added to your history.`,
            });
        } else if (status === 'error' && !isUploadModalOpen) {
            setToast({
                type: 'error',
                message: 'Upload failed. Open the upload window for details.',
            });
        }
    }, [status]);

    // Close mobile drawer on navigation
    useEffect(() => {
        onMobileClose?.();
    }, [location.pathname]);

    // Close settings dropdown when clicking outside both the button and the dropdown
    useEffect(() => {
        const handler = (e) => {
            const inButton = settingsBtnRef.current?.contains(e.target);
            const inDropdown = dropdownRef.current?.contains(e.target);
            if (!inButton && !inDropdown) {
                setIsSettingsOpen(false);
                setShowDeleteConfirm(false);
            }
        };
        document.addEventListener('mousedown', handler);
        return () => document.removeEventListener('mousedown', handler);
    }, []);

    // Fetch current settings whenever the dropdown opens
    useEffect(() => {
        if (!isSettingsOpen) return;
        fetch('/api/user/settings', { credentials: 'include' })
            .then(r => r.json())
            .then(data => setAutoSync(data.auto_sync ?? false))
            .catch(() => {});
    }, [isSettingsOpen]);

    const handleToggleAutoSync = async () => {
        const newValue = !autoSync;
        setAutoSync(newValue);
        setIsTogglingSync(true);
        try {
            await fetch('/api/user/autosync', {
                method: 'POST',
                credentials: 'include',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ enabled: newValue }),
            });
        } catch {
            setAutoSync(!newValue); // revert on network error
        } finally {
            setIsTogglingSync(false);
        }
    };

    const handleDeleteData = async () => {
        setIsDeleting(true);
        try {
            const res = await fetch('/api/user/data', { method: 'DELETE', credentials: 'include' });
            if (res.ok) {
                localStorage.removeItem('activeSessionId');
                sessionStorage.removeItem('uploadJobId');
                navigate('/');
            } else {
                const data = await res.json();
                setToast({ type: 'error', message: 'Failed to delete your data. Please try again.' });
                setIsSettingsOpen(false);
                setShowDeleteConfirm(false);
            }
        } catch (err) {
            setToast({ type: 'error', message: 'Failed to delete data. Is the server running?' });
            setIsSettingsOpen(false);
            setShowDeleteConfirm(false);
        } finally {
            setIsDeleting(false);
        }
    };

    const handleNewChat = () => {
        navigate(`/app`);
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
                    navigate(`/app/${data.session_id}`);
                } else {
                    setToast({ type: 'error', message: 'No previous chat found.' });
                }
            }
        } catch (error) {
            setToast({ type: 'error', message: 'Failed to load previous chat.' });
        } finally {
            setIsLoadingPrevious(false);
        }
    };

    const handleReturnToCurrent = () => {
        if (activeSessionId) {
            navigate(`/app/${activeSessionId}`);
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

                        {/* Settings Button */}
                        <button
                            ref={settingsBtnRef}
                            onClick={() => {
                                const rect = settingsBtnRef.current.getBoundingClientRect();
                                setDropdownPos({
                                    bottom: window.innerHeight - rect.top + 8,
                                    left: rect.left,
                                });
                                setIsSettingsOpen(o => !o);
                                setShowDeleteConfirm(false);
                            }}
                            className="flex items-center p-3 rounded-xl hover:bg-white/5 text-zinc-400 hover:text-white transition-colors group w-full h-[48px] relative overflow-hidden"
                            title={!isExpanded ? "Settings" : ""}
                        >
                            <div className="flex items-center justify-center shrink-0 w-6 h-6">
                                <Settings className="w-5 h-5" />
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
                                        Settings
                                    </motion.span>
                                )}
                            </AnimatePresence>
                        </button>

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

            {/* Mobile drawer — slide-in overlay, hidden on md+ */}
            <AnimatePresence>
                {isMobileOpen && (
                    <>
                        {/* Backdrop */}
                        <motion.div
                            initial={{ opacity: 0 }}
                            animate={{ opacity: 1 }}
                            exit={{ opacity: 0 }}
                            transition={{ duration: 0.2 }}
                            className="fixed inset-0 bg-black/60 z-30 md:hidden"
                            onClick={onMobileClose}
                        />

                        {/* Drawer panel */}
                        <motion.div
                            initial={{ x: '-100%' }}
                            animate={{ x: 0 }}
                            exit={{ x: '-100%' }}
                            transition={{ duration: 0.25, ease: 'easeInOut' }}
                            className="fixed top-0 left-0 h-full w-64 bg-zinc-900 border-r border-white/5 flex flex-col z-40 md:hidden pt-[73px]"
                        >
                            <div className="flex-1 flex flex-col gap-2 px-3 overflow-hidden mt-2">
                                <div className="flex-1 flex flex-col gap-2">
                                    <button
                                        onClick={handleNewChat}
                                        className="flex items-center gap-3 p-3 rounded-xl hover:bg-white/5 text-zinc-300 hover:text-white transition-colors w-full"
                                    >
                                        <Plus className="w-5 h-5 shrink-0" />
                                        <span className="font-medium">New Chat</span>
                                    </button>

                                    <button
                                        onClick={handlePreviousChat}
                                        disabled={isLoadingPrevious || isProcessing}
                                        className="flex items-center gap-3 p-3 rounded-xl hover:bg-white/5 text-zinc-300 hover:text-white transition-colors w-full disabled:opacity-50"
                                    >
                                        <MessageSquare className="w-5 h-5 shrink-0" />
                                        <span className="text-sm">Previous Chat</span>
                                    </button>

                                    {isViewingPrevious && (
                                        <button
                                            onClick={handleReturnToCurrent}
                                            className="flex items-center gap-3 p-3 rounded-xl hover:bg-spotify-green/10 text-spotify-green transition-colors w-full"
                                        >
                                            <ChevronRight className="w-5 h-5 shrink-0" />
                                            <span className="text-sm font-medium">Return to current</span>
                                        </button>
                                    )}
                                </div>

                                <div className="pb-4 flex flex-col gap-2">
                                    <div className="my-1 border-t border-white/5 mx-2" />

                                    <button
                                        ref={settingsBtnRef}
                                        onClick={() => {
                                            const rect = settingsBtnRef.current.getBoundingClientRect();
                                            setDropdownPos({
                                                bottom: window.innerHeight - rect.top + 8,
                                                left: rect.left,
                                            });
                                            setIsSettingsOpen(o => !o);
                                            setShowDeleteConfirm(false);
                                        }}
                                        className="flex items-center gap-3 p-3 rounded-xl hover:bg-white/5 text-zinc-400 hover:text-white transition-colors w-full"
                                    >
                                        <Settings className="w-5 h-5 shrink-0" />
                                        <span className="text-sm font-medium">Settings</span>
                                    </button>

                                    <button
                                        onClick={() => { setIsUploadModalOpen(true); onMobileClose?.(); }}
                                        className="flex items-center gap-3 p-3 rounded-xl hover:bg-spotify-green/10 text-spotify-green transition-colors w-full"
                                    >
                                        <UploadCloud className="w-5 h-5 shrink-0" />
                                        <span className="text-sm font-medium">Upload History</span>
                                    </button>
                                </div>
                            </div>
                        </motion.div>
                    </>
                )}
            </AnimatePresence>

            {/* Upload Modal Overlay */}
            <UploadModal
                isOpen={isUploadModalOpen}
                onClose={() => setIsUploadModalOpen(false)}
                status={status}
                progress={progress}
                message={message}
                totalEvents={totalEvents}
                startJob={startJob}
                resetJob={resetJob}
            />

            {/* Toast notification — fixed bottom-right */}
            <AnimatePresence>
                {toast && (
                    <div className="fixed bottom-6 right-6 z-50">
                        <Toast
                            type={toast.type}
                            message={toast.message}
                            onClose={() => setToast(null)}
                        />
                    </div>
                )}
            </AnimatePresence>

            {/* Settings dropdown — rendered via portal so it escapes overflow-hidden */}
            {createPortal(
                <AnimatePresence>
                    {isSettingsOpen && (
                        <motion.div
                            ref={dropdownRef}
                            initial={{ opacity: 0, y: 6, scale: 0.97 }}
                            animate={{ opacity: 1, y: 0, scale: 1 }}
                            exit={{ opacity: 0, y: 6, scale: 0.97 }}
                            transition={{ duration: 0.15 }}
                            style={{ bottom: dropdownPos.bottom, left: dropdownPos.left }}
                            className="fixed w-56 bg-zinc-800 border border-white/10 rounded-xl shadow-2xl overflow-hidden z-50"
                        >
                            {!showDeleteConfirm ? (
                                <>
                                    {/* Auto-sync toggle */}
                                    <div className="flex items-center justify-between px-4 py-3 border-b border-white/5">
                                        <div className="flex items-center gap-2">
                                            <RefreshCw className="w-4 h-4 text-zinc-400 flex-shrink-0" />
                                            <span className="text-sm text-zinc-300">Auto-sync history</span>
                                        </div>
                                        <button
                                            onClick={handleToggleAutoSync}
                                            disabled={isTogglingSync}
                                            className={`relative w-9 h-5 rounded-full transition-colors flex-shrink-0 ${autoSync ? 'bg-spotify-green' : 'bg-zinc-600'} disabled:opacity-50`}
                                            title={autoSync ? 'Disable auto-sync' : 'Enable auto-sync'}
                                        >
                                            <span className={`absolute top-0.5 left-0.5 w-4 h-4 rounded-full bg-white shadow transition-transform ${autoSync ? 'translate-x-4' : 'translate-x-0'}`} />
                                        </button>
                                    </div>

                                    {/* Tutorial */}
                                    <button
                                        onClick={() => { onShowTutorial?.(); setIsSettingsOpen(false); }}
                                        className="flex items-center gap-3 w-full px-4 py-3 text-sm text-zinc-300 hover:bg-white/5 transition-colors"
                                    >
                                        <BookOpen className="w-4 h-4 flex-shrink-0" />
                                        View tutorial
                                    </button>

                                    {/* Delete data */}
                                    <button
                                        onClick={() => setShowDeleteConfirm(true)}
                                        className="flex items-center gap-3 w-full px-4 py-3 text-sm text-red-400 hover:bg-red-500/10 transition-colors"
                                    >
                                        <Trash2 className="w-4 h-4 flex-shrink-0" />
                                        Delete my data
                                    </button>
                                </>
                            ) : (
                                <div className="p-4 flex flex-col gap-3">
                                    <div className="flex items-start gap-2">
                                        <AlertTriangle className="w-4 h-4 text-red-400 flex-shrink-0 mt-0.5" />
                                        <p className="text-xs text-zinc-300 leading-relaxed">
                                            This will permanently delete your listening history, chat sessions, and account data. This cannot be undone.
                                        </p>
                                    </div>
                                    <div className="flex gap-2">
                                        <button
                                            onClick={() => setShowDeleteConfirm(false)}
                                            disabled={isDeleting}
                                            className="flex-1 py-1.5 rounded-lg text-xs text-zinc-400 hover:text-white bg-white/5 hover:bg-white/10 transition-colors disabled:opacity-50 disabled:pointer-events-none"
                                        >
                                            Cancel
                                        </button>
                                        <button
                                            onClick={handleDeleteData}
                                            disabled={isDeleting}
                                            className="flex-1 py-1.5 rounded-lg text-xs text-white bg-red-600 hover:bg-red-500 transition-colors disabled:opacity-50"
                                        >
                                            {isDeleting ? 'Deleting...' : 'Delete'}
                                        </button>
                                    </div>
                                </div>
                            )}
                        </motion.div>
                    )}
                </AnimatePresence>,
                document.body
            )}
        </>
    );
}

export default Sidebar;