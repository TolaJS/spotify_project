import React, { useState, useRef } from 'react';
import { X, UploadCloud, FileJson, CheckCircle, AlertCircle, Disc3, Trash2 } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';

function formatBytes(bytes) {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function UploadModal({ isOpen, onClose, status, progress, message, totalEvents, startJob, resetJob }) {
    const [isDragging, setIsDragging] = useState(false);
    const [selectedFiles, setSelectedFiles] = useState([]);
    // localStatus drives the idle/selected/uploading states before a job exists
    const [localStatus, setLocalStatus] = useState('idle');
    const [uploadError, setUploadError] = useState('');
    const [gcsProgress, setGcsProgress] = useState(0);
    const [gcsMessage, setGcsMessage] = useState('');
    const fileInputRef = useRef(null);

    // The active display status: job state takes over once a job is running
    const activeStatus = (status === 'processing' || status === 'complete' || status === 'error')
        ? status
        : localStatus;

    const addFiles = (newFiles) => {
        const all = Array.from(newFiles);
        const valid = all.filter(f => f.name.endsWith('.json'));
        if (all.length > 0 && valid.length === 0) {
            setUploadError('Only .json files are accepted. Please select your Spotify Extended Streaming History files.');
            return;
        }
        setUploadError('');
        setSelectedFiles(prev => {
            const existing = new Set(prev.map(f => f.name));
            const deduped = valid.filter(f => !existing.has(f.name));
            return [...prev, ...deduped];
        });
        setLocalStatus('selected');
    };

    const removeFile = (index) => {
        setSelectedFiles(prev => {
            const next = prev.filter((_, i) => i !== index);
            if (next.length === 0) setLocalStatus('idle');
            return next;
        });
    };

    const handleUpload = async () => {
        if (!selectedFiles.length) return;
        setLocalStatus('uploading');
        setUploadError('');

        if (import.meta.env.VITE_USE_GCS_UPLOAD === 'true') {
            // ── Production: upload directly to GCS via signed URLs ──
            try {
                // 1. Request a signed URL for each file
                const urlRes = await fetch('/api/upload/signed-urls', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    credentials: 'include',
                    body: JSON.stringify({ files: selectedFiles.map(f => ({ filename: f.name, size: f.size })) }),
                });
                const urlData = await urlRes.json();
                if (!urlRes.ok) {
                    setLocalStatus('selected');
                    setUploadError(urlData.detail ?? 'Failed to get upload URLs.');
                    return;
                }

                // 2. Upload each file directly to GCS with per-file progress tracking
                const gcsPaths = [];
                const totalBytes = selectedFiles.reduce((sum, f) => sum + f.size, 0);
                let bytesUploaded = 0;

                const uploadWithProgress = (url, file) => new Promise((resolve, reject) => {
                    const xhr = new XMLHttpRequest();
                    xhr.open('PUT', url);
                    xhr.setRequestHeader('Content-Type', 'application/json');
                    xhr.upload.addEventListener('progress', (e) => {
                        if (e.lengthComputable) {
                            const pct = Math.round(((bytesUploaded + e.loaded) / totalBytes) * 100);
                            setGcsProgress(pct);
                            setGcsMessage(`Uploading ${file.name}... ${pct}%`);
                        }
                    });
                    xhr.addEventListener('load', () => {
                        if (xhr.status >= 200 && xhr.status < 300) {
                            bytesUploaded += file.size;
                            resolve();
                        } else {
                            reject(new Error(`${xhr.status}`));
                        }
                    });
                    xhr.addEventListener('error', () => reject(new Error('Network error')));
                    xhr.send(file);
                });

                for (let i = 0; i < selectedFiles.length; i++) {
                    const { upload_url, gcs_path } = urlData.files[i];
                    try {
                        await uploadWithProgress(upload_url, selectedFiles[i]);
                    } catch (err) {
                        setLocalStatus('selected');
                        setGcsProgress(0);
                        setGcsMessage('');
                        setUploadError(`Failed to upload ${selectedFiles[i].name}. Please try again.`);
                        return;
                    }
                    gcsPaths.push(gcs_path);
                }

                // 3. Tell the backend to ingest the uploaded files
                const ingestRes = await fetch('/api/upload/ingest', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    credentials: 'include',
                    body: JSON.stringify({ gcs_paths: gcsPaths }),
                });
                const ingestData = await ingestRes.json();
                if (!ingestRes.ok) {
                    setLocalStatus('selected');
                    setUploadError(ingestData.detail ?? 'Failed to start ingestion.');
                    return;
                }
                setSelectedFiles([]);
                setGcsProgress(0);
                setGcsMessage('');
                startJob(ingestData.job_id);
            } catch (err) {
                setLocalStatus('selected');
                setUploadError('Upload failed. Please try again.');
            }
        } else {
            // ── Local dev: send files directly to the backend ──
            const formData = new FormData();
            selectedFiles.forEach(f => formData.append('files', f));
            try {
                const res = await fetch('/api/upload', {
                    method: 'POST',
                    body: formData,
                    credentials: 'include',
                });
                const data = await res.json();
                if (!res.ok) {
                    setLocalStatus('selected');
                    setUploadError(data.detail ?? 'Upload failed.');
                    return;
                }
                setSelectedFiles([]);
                startJob(data.job_id);
            } catch (err) {
                setLocalStatus('selected');
                setUploadError('Upload failed. Is the server running?');
            }
        }
    };

    const handleDragOver = (e) => { e.preventDefault(); setIsDragging(true); };
    const handleDragLeave = () => setIsDragging(false);
    const handleDrop = (e) => {
        e.preventDefault();
        setIsDragging(false);
        addFiles(e.dataTransfer.files);
    };
    const handleBrowse = (e) => {
        addFiles(e.target.files);
        e.target.value = '';
    };

    const handleClose = () => {
        // If a job is running, leave it — polling continues in the hook
        // If idle/done/error, reset local state
        if (activeStatus !== 'processing' && activeStatus !== 'uploading') {
            resetJob();
            setSelectedFiles([]);
            setLocalStatus('idle');
            setUploadError('');
        }
        setIsDragging(false);
        onClose();
    };

    if (!isOpen) return null;

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
                            <button onClick={handleClose} className="text-zinc-400 hover:text-white hover:bg-white/5 p-2 rounded-full transition-colors">
                                <X className="w-5 h-5" />
                            </button>
                        </div>

                        <div className="p-6 md:p-8 flex flex-col items-center max-h-[75vh] overflow-y-auto scrollbar-none [&::-webkit-scrollbar]:hidden [-ms-overflow-style:none] [scrollbar-width:none]">

                            {/* ── Idle / Selected ── */}
                            {(activeStatus === 'idle' || activeStatus === 'selected') && (
                                <>
                                    <p className="text-zinc-400 text-center mb-6 text-sm leading-relaxed">
                                        Upload your Spotify Extended Streaming History files (JSON). You can upload multiple files at once.
                                    </p>

                                    <div
                                        onDragOver={handleDragOver}
                                        onDragLeave={handleDragLeave}
                                        onDrop={handleDrop}
                                        className={`w-full border-2 border-dashed rounded-xl flex flex-col items-center justify-center py-8 px-6 transition-all duration-200 ${
                                            isDragging
                                                ? 'border-spotify-green bg-spotify-green/5'
                                                : 'border-white/10 bg-zinc-800/30 hover:border-white/20 hover:bg-zinc-800/50'
                                        }`}
                                    >
                                        <div className={`w-14 h-14 rounded-full flex items-center justify-center mb-3 ${isDragging ? 'bg-spotify-green text-black' : 'bg-zinc-800 text-spotify-green border border-white/5'}`}>
                                            <UploadCloud className="w-7 h-7" />
                                        </div>
                                        <h3 className="text-base font-bold text-white mb-1">
                                            {isDragging ? 'Drop files here' : 'Drag and drop your JSON files'}
                                        </h3>
                                        <p className="text-sm text-zinc-500 text-center mb-4">or click to browse</p>
                                        <button
                                            onClick={() => fileInputRef.current?.click()}
                                            className="bg-white/10 hover:bg-white/20 text-white font-medium py-2 px-5 rounded-full transition-colors flex items-center space-x-2 text-sm"
                                        >
                                            <FileJson className="w-4 h-4" />
                                            <span>Browse Files</span>
                                        </button>
                                        <input
                                            ref={fileInputRef}
                                            type="file"
                                            accept=".json"
                                            multiple
                                            className="hidden"
                                            onChange={handleBrowse}
                                        />
                                    </div>

                                    {uploadError && (
                                        <p className="mt-3 text-red-400 text-sm text-center">{uploadError}</p>
                                    )}

                                    {selectedFiles.length > 0 && (
                                        <div className="w-full mt-4 flex flex-col gap-2">
                                            <div className="flex flex-col gap-2 max-h-48 overflow-y-auto pr-1 scrollbar-none [&::-webkit-scrollbar]:hidden [-ms-overflow-style:none] [scrollbar-width:none]">
                                                {selectedFiles.map((file, i) => (
                                                    <div key={i} className="flex items-center justify-between bg-zinc-800/60 border border-white/5 rounded-lg px-4 py-2 flex-shrink-0">
                                                        <div className="flex items-center gap-3 min-w-0">
                                                            <FileJson className="w-4 h-4 text-spotify-green flex-shrink-0" />
                                                            <span className="text-white text-sm truncate">{file.name}</span>
                                                        </div>
                                                        <div className="flex items-center gap-3 flex-shrink-0 ml-3">
                                                            <span className="text-zinc-500 text-xs">{formatBytes(file.size)}</span>
                                                            <button onClick={() => removeFile(i)} className="text-zinc-500 hover:text-red-400 transition-colors">
                                                                <Trash2 className="w-4 h-4" />
                                                            </button>
                                                        </div>
                                                    </div>
                                                ))}
                                            </div>
                                            <button
                                                onClick={handleUpload}
                                                className="mt-2 w-full bg-spotify-green hover:bg-spotify-green/90 text-black font-semibold py-2.5 rounded-full transition-colors text-sm"
                                            >
                                                Upload {selectedFiles.length} file{selectedFiles.length > 1 ? 's' : ''}
                                            </button>
                                        </div>
                                    )}
                                </>
                            )}

                            {/* ── Uploading / Processing ── */}
                            {(activeStatus === 'uploading' || activeStatus === 'processing') && (() => {
                                const displayProgress = activeStatus === 'uploading' ? gcsProgress : progress;
                                const displayMessage = activeStatus === 'uploading'
                                    ? (gcsMessage || 'Uploading...')
                                    : (message || 'Processing...');
                                // Show the bar only during GCS file upload or once buffering starts (≥55%)
                                const showBar = activeStatus === 'uploading' || displayProgress >= 55;
                                const barPct = activeStatus === 'uploading'
                                    ? displayProgress
                                    : Math.round(Math.max(0, (displayProgress - 55) / 45 * 100));
                                return (
                                    <div className="w-full flex flex-col items-center gap-6 py-4">
                                        <Disc3 className="w-10 h-10 text-spotify-green animate-spin" />
                                        <p className="text-white font-medium text-center">{displayMessage}</p>
                                        {showBar && (
                                            <>
                                                <div className="w-full bg-zinc-700 rounded-full h-2.5 overflow-hidden">
                                                    <motion.div
                                                        className="h-full bg-spotify-green rounded-full"
                                                        animate={{ width: `${barPct}%` }}
                                                        transition={{ duration: 0.2 }}
                                                    />
                                                </div>
                                                <p className="text-zinc-500 text-sm">{barPct}% complete</p>
                                            </>
                                        )}
                                        <p className="text-zinc-600 text-xs text-center">
                                            You can close this window — ingestion will continue in the background.
                                        </p>
                                    </div>
                                );
                            })()}

                            {/* ── Complete ── */}
                            {activeStatus === 'complete' && (
                                <div className="w-full flex flex-col items-center gap-4 py-4">
                                    <CheckCircle className="w-14 h-14 text-spotify-green" />
                                    <p className="text-white text-lg font-bold">History Ingested!</p>
                                    {totalEvents != null && (
                                        <p className="text-zinc-400 text-sm">
                                            {totalEvents.toLocaleString()} listening events added to your graph.
                                        </p>
                                    )}
                                    <p className="text-zinc-500 text-sm text-center">
                                        You can now ask questions about your full listening history.
                                    </p>
                                    <button
                                        onClick={handleClose}
                                        className="mt-2 bg-spotify-green hover:bg-spotify-green/90 text-black font-semibold py-2 px-8 rounded-full transition-colors"
                                    >
                                        Start Chatting
                                    </button>
                                </div>
                            )}

                            {/* ── Error ── */}
                            {activeStatus === 'error' && (
                                <div className="w-full flex flex-col items-center gap-4 py-4">
                                    <AlertCircle className="w-14 h-14 text-red-500" />
                                    <p className="text-white text-lg font-bold">Something went wrong</p>
                                    <p className="text-zinc-400 text-sm text-center">{message}</p>
                                    <button
                                        onClick={() => { resetJob(); setLocalStatus('idle'); setUploadError(''); }}
                                        className="mt-2 bg-white/10 hover:bg-white/20 text-white font-medium py-2 px-6 rounded-full transition-colors"
                                    >
                                        Try Again
                                    </button>
                                </div>
                            )}

                        </div>
                    </motion.div>
                </div>
            )}
        </AnimatePresence>
    );
}

export default UploadModal;
