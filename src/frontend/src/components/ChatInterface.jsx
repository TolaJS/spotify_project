import React, { useState, useEffect, useRef } from 'react';
import { useParams, useNavigate, useLocation } from 'react-router-dom';
import { motion, AnimatePresence } from 'framer-motion';
import ChatFeed from './ChatFeed';
import InputArea from './InputArea';

const SUGGESTIONS = [
    "Play upbeat indie rock",
    "Analyze my top tracks",
    "Who produced this song?",
    "Queue some lofi beats"
];

const USER_TIMEZONE = Intl.DateTimeFormat().resolvedOptions().timeZone;

function ChatInterface({ onProcessingChange, userId }) {
    const { chatId } = useParams();
    const navigate = useNavigate();
    const location = useLocation();

    const [messages, setMessages] = useState([]);
    const [isConnecting, setIsConnecting] = useState(!!chatId);
    const [socket, setSocket] = useState(null);
    const [connectionError, setConnectionError] = useState(null);
    const [isProcessing, setIsProcessing] = useState(false);

    const setProcessing = (value) => {
        setIsProcessing(value);
        onProcessingChange?.(value);
    };

    const [currentMessageId, setCurrentMessageId] = useState(null);

    const endOfMessagesRef = useRef(null);
    const activeMessageIdRef = useRef(null);

    // Reset and load chat history when navigating to a new chat ID
    useEffect(() => {
        let isMounted = true;
        setMessages([]);
        setProcessing(false);
        activeMessageIdRef.current = null;
        setCurrentMessageId(null);

        const loadHistory = async () => {
            if (!chatId) return;
            try {
                const response = await fetch(`/api/chats/${chatId}`, {
                    credentials: "include"
                });
                if (!response.ok) return;
                
                const data = await response.json();
                if (data.turns && data.turns.length > 0 && isMounted) {
                    const historyMessages = [];
                    data.turns.forEach(turn => {
                        // Reconstruct User prompt
                        historyMessages.push({
                            id: `hist-user-${turn.timestamp}`,
                            text: turn.query,
                            sender: 'user'
                        });
                        // Reconstruct Bot response
                        historyMessages.push({
                            id: `hist-bot-${turn.timestamp}`,
                            text: turn.response,
                            sender: 'agent',
                            isFinal: true
                        });
                    });
                    setMessages(historyMessages);
                }
            } catch (err) {
                console.error("Failed to load chat history:", err);
            }
        };

        loadHistory();

        return () => {
            isMounted = false;
        };
    }, [chatId]);

    // Auto-scroll to bottom whenever messages update.
    // Use 'instant' when history first loads (isConnecting just finished) so mobile
    // doesn't get stuck mid-thread; use 'smooth' for new messages during a live chat.
    const prevMessageCountRef = useRef(0);
    useEffect(() => {
        const isInitialLoad = prevMessageCountRef.current === 0 && messages.length > 0;
        endOfMessagesRef.current?.scrollIntoView({ behavior: isInitialLoad ? 'instant' : 'smooth' });
        prevMessageCountRef.current = messages.length;
    }, [messages]);

    useEffect(() => {
        if (!chatId) {
            setIsConnecting(false);
            return;
        }

        let isMounted = true;
        let pingInterval = null;
        const ws = new WebSocket(import.meta.env.VITE_WS_URL);
        const session = chatId;

        ws.onopen = () => {
            if (!isMounted) return;
            setIsConnecting(false);
            setConnectionError(null);
            // Initiate handshake
            ws.send(JSON.stringify({ session_id: session, user_id: userId }));

            // Keepalive ping every 30s to prevent Cloud Run idle timeout
            pingInterval = setInterval(() => {
                if (ws.readyState === WebSocket.OPEN) {
                    ws.send(JSON.stringify({ type: 'ping' }));
                }
            }, 30000);

            // If a prompt was passed via navigation state, send it immediately
            if (location.state?.initialPrompt) {
                const prompt = location.state.initialPrompt;

                // Clear the state so it doesn't trigger again on component re-renders
                navigate(location.pathname, { replace: true, state: {} });

                // Confirm this session as the active one (may already be set, but be safe)
                localStorage.setItem('activeSessionId', session);

                const newMessageId = Date.now().toString() + Math.random().toString();
                activeMessageIdRef.current = newMessageId;
                setCurrentMessageId(newMessageId);
                setProcessing(true);
                setMessages(prev => [...prev, { id: Date.now() + Math.random(), text: prompt, sender: 'user' }]);

                ws.send(JSON.stringify({
                    query: prompt,
                    session_id: session,
                    message_id: newMessageId,
                    timezone: USER_TIMEZONE
                }));
            }
        };

        ws.onmessage = (event) => {
            if (!isMounted) return;
            const data = JSON.parse(event.data);
            
            // If the incoming message has a message_id and it doesn't match our active request, ignore it.
            if (data.metadata?.message_id && data.metadata.message_id !== activeMessageIdRef.current) {
                return;
            }

            switch (data.type) {
                case 'status':
                    if (!activeMessageIdRef.current) return;
                    
                    setMessages(prev => {
                        const existingMsgIndex = prev.findIndex(m => m.id === activeMessageIdRef.current);
                        if (existingMsgIndex >= 0) {
                            const newMessages = [...prev];
                            newMessages[existingMsgIndex] = { ...newMessages[existingMsgIndex], text: data.content };
                            return newMessages;
                        } else {
                            return [...prev, { id: activeMessageIdRef.current, text: data.content, sender: 'agent', isStatus: true }];
                        }
                    });
                    break;

                case 'result':
                    if (!activeMessageIdRef.current) return;
                    const resultId = activeMessageIdRef.current;
                    setProcessing(false);
                    activeMessageIdRef.current = null;
                    setCurrentMessageId(null);
                    setMessages(prev => {
                        const existingMsgIndex = prev.findIndex(m => m.id === resultId);
                        if (existingMsgIndex >= 0) {
                            const newMessages = [...prev];
                            newMessages[existingMsgIndex] = {
                                ...newMessages[existingMsgIndex],
                                isStatus: false,
                                isFinal: true,
                                text: data.content,
                                metadata: data.metadata
                            };
                            return newMessages;
                        }
                        // Fallback if status never arrived
                        return [...prev, {
                            id: resultId,
                            text: data.content,
                            sender: 'agent',
                            isFinal: true,
                            metadata: data.metadata
                        }];
                    });
                    break;

                case 'error':
                    if (!activeMessageIdRef.current) return;
                    const errorId = activeMessageIdRef.current;
                    setProcessing(false);
                    activeMessageIdRef.current = null;
                    setCurrentMessageId(null);
                    setMessages(prev => {
                        const existingMsgIndex = prev.findIndex(m => m.id === errorId);
                        if (existingMsgIndex >= 0) {
                            const newMessages = [...prev];
                            newMessages[existingMsgIndex] = {
                                ...newMessages[existingMsgIndex],
                                isStatus: false,
                                text: `Error: ${data.content}`,
                                sender: 'system',
                                isError: true
                            };
                            return newMessages;
                        }
                        return prev;
                    });
                    break;

                default:
                    console.warn('Unknown message type:', data);
            }
        };

        ws.onclose = () => {
            if (!isMounted) return;
            setIsConnecting(false);
            setConnectionError("Disconnected from server.");
        };

        ws.onerror = (err) => {
            if (!isMounted) return;
            console.error("WebSocket error:", err);
            setConnectionError("Failed to connect to the assistant server.");
            ws.close();
        };

        setSocket(ws);

        return () => {
            isMounted = false;
            setProcessing(false);
            clearInterval(pingInterval);

            // Tell the backend to save this session to Firestore before we disconnect/navigate away.
            // We use save_session_only on the backend so the session stays in memory
            // until the WebSocket disconnect actually evicts it.
            if (session && session !== 'local_dev_user') {
                try {
                    fetch(`/api/chats/${session}/save`, {
                        method: 'POST',
                        credentials: 'include',
                        keepalive: true
                    }).catch(err => console.error("Failed to save session on exit:", err));
                } catch (e) {
                    console.error("Save session error:", e);
                }
            }

            ws.close();
        };
    }, [chatId]);

    const handleSendMessage = (text) => {
        if (!text.trim() || isProcessing) return;

        // If we are on the empty state screen, navigate to a new chat and pass the prompt
        if (!chatId) {
            const uniqueId = Date.now().toString(36) + Math.random().toString(36).substring(2, 7);
            localStorage.setItem('activeSessionId', uniqueId);
            navigate(`/app/${uniqueId}`, { state: { initialPrompt: text } });
            return;
        }

        if (!socket || socket.readyState !== WebSocket.OPEN) return;

        // Mark this session as the user's active (current) conversation
        localStorage.setItem('activeSessionId', chatId);

        const newMessageId = Date.now().toString() + Math.random().toString();
        const session = chatId;
        activeMessageIdRef.current = newMessageId;
        setCurrentMessageId(newMessageId);
        setProcessing(true);
        setMessages(prev => [...prev, { id: Date.now() + Math.random(), text, sender: 'user' }]);
        
        socket.send(JSON.stringify({
            query: text,
            session_id: session,
            message_id: newMessageId,
            timezone: USER_TIMEZONE
        }));
    };

    const handleStopMessage = () => {
        const stoppedId = activeMessageIdRef.current;
        activeMessageIdRef.current = null;
        setCurrentMessageId(null);
        setProcessing(false);
        setMessages(prev => {
            const existingMsgIndex = prev.findIndex(m => m.id === stoppedId);
            if (existingMsgIndex >= 0) {
                const newMessages = [...prev];
                newMessages[existingMsgIndex] = {
                    ...newMessages[existingMsgIndex],
                    isStatus: false,
                    isCancelledInfo: true,
                    text: "Response stopped by user.",
                    sender: 'system' // Keep sender as system so MessageBubble renders it properly
                };
                return newMessages;
            }
            return prev;
        });
    };

    if (connectionError) {
        return (
            <div className="h-full flex items-center justify-center flex-col text-center px-4">
                <div className="mb-4 text-red-500 text-5xl">⚠️</div>
                <h2 className="text-2xl font-bold mb-2 text-white">Connection Lost</h2>
                <p className="text-zinc-400 mb-6 max-w-md">{connectionError}</p>
                <button
                    onClick={() => window.location.reload()}
                    className="bg-zinc-800 hover:bg-zinc-700 px-6 py-2 rounded-full font-semibold text-white transition-colors border border-white/10"
                >
                    Reconnect
                </button>
            </div>
        );
    }

    if (isConnecting) {
        return (
            <div className="h-full flex items-center justify-center flex-col">
                <div className="w-10 h-10 border-4 border-zinc-800 border-t-spotify-green rounded-full animate-spin mb-4"></div>
                <p className="text-zinc-400 font-medium animate-pulse">Connecting to backend...</p>
            </div>
        );
    }

    const showSuggestions = messages.length === 0;

    return (
        <div className="flex-1 w-full h-full flex flex-col bg-spotify-darkest relative max-w-4xl mx-auto">
            <div className="flex-1 overflow-y-auto p-4 md:p-8 custom-scrollbar">
                <ChatFeed messages={messages} />
                <div ref={endOfMessagesRef} />
            </div>

            <div className="w-full p-4 md:px-8 pb-6 bg-spotify-darkest flex flex-col items-center shrink-0">
                <div className="w-full max-w-3xl">
                    <AnimatePresence>
                        {showSuggestions && (
                            <motion.div 
                                initial={{ opacity: 0, y: 10 }}
                                animate={{ opacity: 1, y: 0 }}
                                exit={{ opacity: 0, y: 10 }}
                                className="flex flex-wrap justify-center gap-2 mb-4"
                            >
                                {SUGGESTIONS.map((suggestion, idx) => (
                                    <button
                                        key={idx}
                                        onClick={() => handleSendMessage(suggestion)}
                                        className="text-xs md:text-sm bg-zinc-800/80 hover:bg-zinc-700/80 text-zinc-300 hover:text-white px-4 py-2 rounded-full transition-all border border-white/5 shadow-sm backdrop-blur-sm"
                                    >
                                        {suggestion}
                                    </button>
                                ))}
                            </motion.div>
                        )}
                    </AnimatePresence>
                    <InputArea onSend={handleSendMessage} onStop={handleStopMessage} isProcessing={isProcessing} disabled={chatId ? socket?.readyState !== WebSocket.OPEN : false} />
                </div>
            </div>
        </div>
    );
}

export default ChatInterface;