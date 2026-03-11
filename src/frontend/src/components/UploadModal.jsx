import React, { useState } from 'react';
import { X, UploadCloud, FileJson } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';

function UploadModal({ isOpen, onClose }) {
    const [isDragging, setIsDragging] = useState(false);

    if (!isOpen) return null;

    const handleDragOver = (e) => {
        e.preventDefault();
        setIsDragging(true);
    };

    const handleDragLeave = () => {
        setIsDragging(false);
    };

    const handleDrop = (e) => {
        e.preventDefault();
        setIsDragging(false);
        // Placeholder for file handling logic
        const files = e.dataTransfer.files;
        if (files.length > 0) {
            console.log("File dropped:", files[0].name);
        }
    };

    return (
        <AnimatePresence>
            {isOpen && (
                <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4">
                    <motion.div 
                        initial={{ opacity: 0, scale: 0.95, y: 20 }}
                        animate={{ opacity: 1, scale: 1, y: 0 }}
                        exit={{ opacity: 0, scale: 0.95, y: 20 }}
                        className="bg-zinc-900 border border-white/10 rounded-2xl shadow-2xl w-full max-w-lg overflow-hidden flex flex-col"
                    >
                        {/* Header */}
                        <div className="flex items-center justify-between px-6 py-4 border-b border-white/5 bg-zinc-900/50">
                            <h2 className="text-xl font-bold text-white tracking-tight">Upload Extended History</h2>
                            <button 
                                onClick={onClose}
                                className="text-zinc-400 hover:text-white hover:bg-white/5 p-2 rounded-full transition-colors"
                            >
                                <X className="w-5 h-5" />
                            </button>
                        </div>

                        {/* Body */}
                        <div className="p-6 md:p-8 flex flex-col items-center">
                            <p className="text-zinc-400 text-center mb-6 text-sm leading-relaxed">
                                Upload your Spotify Extended Streaming History (JSON) to give the AI Assistant deep insights into your lifetime listening habits.
                            </p>

                            {/* Drag & Drop Zone */}
                            <div 
                                onDragOver={handleDragOver}
                                onDragLeave={handleDragLeave}
                                onDrop={handleDrop}
                                className={`w-full border-2 border-dashed rounded-xl flex flex-col items-center justify-center py-12 px-6 transition-all duration-200 ${
                                    isDragging 
                                    ? 'border-spotify-green bg-spotify-green/5' 
                                    : 'border-white/10 bg-zinc-800/30 hover:border-white/20 hover:bg-zinc-800/50'
                                }`}
                            >
                                <div className={`w-16 h-16 rounded-full flex items-center justify-center mb-4 shadow-sm ${isDragging ? 'bg-spotify-green text-black' : 'bg-zinc-800 text-spotify-green border border-white/5'}`}>
                                    <UploadCloud className="w-8 h-8" />
                                </div>
                                <h3 className="text-lg font-bold text-white mb-2">
                                    {isDragging ? 'Drop file here' : 'Drag and drop your JSON'}
                                </h3>
                                <p className="text-sm text-zinc-500 text-center max-w-xs mb-6">
                                    or click to browse your files.
                                </p>
                                <button className="bg-white/10 hover:bg-white/20 text-white font-medium py-2 px-6 rounded-full transition-colors flex items-center space-x-2 text-sm">
                                    <FileJson className="w-4 h-4" />
                                    <span>Browse Files</span>
                                </button>
                            </div>
                        </div>
                    </motion.div>
                </div>
            )}
        </AnimatePresence>
    );
}

export default UploadModal;