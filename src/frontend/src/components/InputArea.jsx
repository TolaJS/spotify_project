import React, { useState, useRef, useEffect } from 'react';
import { SendHorizonal, Square } from 'lucide-react';

function InputArea({ onSend, onStop, isProcessing, disabled }) {
    const [text, setText] = useState('');
    const [history, setHistory] = useState([]);
    const [historyIndex, setHistoryIndex] = useState(-1);
    const textareaRef = useRef(null);

    const handleSend = () => {
        if (text.trim() && !disabled && !isProcessing) {
            onSend(text);
            setHistory(prev => [...prev, text]);
            setHistoryIndex(-1);
            setText('');
        }
    };

    const handleKeyDown = (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            if (!isProcessing) {
                handleSend();
            }
        } else if (e.key === 'Escape') {
            if (isProcessing) {
                e.preventDefault();
                onStop();
            }
        } else if (e.key === 'ArrowUp') {
            if (history.length > 0 && !isProcessing) {
                e.preventDefault();
                const newIndex = historyIndex === -1 ? history.length - 1 : Math.max(0, historyIndex - 1);
                setHistoryIndex(newIndex);
                setText(history[newIndex]);
            }
        } else if (e.key === 'ArrowDown') {
            if (historyIndex !== -1 && !isProcessing) {
                e.preventDefault();
                const newIndex = historyIndex + 1;
                if (newIndex >= history.length) {
                    setHistoryIndex(-1);
                    setText('');
                } else {
                    setHistoryIndex(newIndex);
                    setText(history[newIndex]);
                }
            }
        }
    };

    // Auto-resize textarea
    useEffect(() => {
        if (textareaRef.current) {
            textareaRef.current.style.height = 'auto';
            textareaRef.current.style.height = Math.min(textareaRef.current.scrollHeight, 120) + 'px';
        }
    }, [text]);

    return (
        <div className={`relative flex items-end w-full bg-zinc-800/80 backdrop-blur-md rounded-2xl border ${isProcessing ? 'border-white/5 opacity-80' : 'border-white/10 focus-within:border-white/20'} transition-all shadow-xl`}>
            <textarea
                ref={textareaRef}
                value={text}
                onChange={(e) => setText(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder="Ask the AI to play music, analyze your history..."
                className="w-full bg-transparent text-white placeholder-zinc-500 px-4 py-3.5 outline-none resize-none max-h-32 min-h-[52px] rounded-2xl custom-scrollbar"
                rows={1}
                disabled={disabled}
            />
            {isProcessing ? (
                <button
                    onClick={onStop}
                    disabled={disabled}
                    className="text-zinc-400 hover:text-red-400 p-3.5 transition-colors shrink-0"
                    title="Stop generating"
                >
                    <Square className="w-5 h-5 fill-current" />
                </button>
            ) : (
                <button
                    onClick={handleSend}
                    disabled={!text.trim() || disabled}
                    className="text-spotify-green hover:text-[#1ed760] disabled:text-zinc-600 p-3.5 transition-colors shrink-0"
                    title="Send prompt"
                >
                    <SendHorizonal className="w-5 h-5" />
                </button>
            )}
        </div>
    );
}

export default InputArea;