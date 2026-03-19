import { useState, useEffect, useRef, useCallback } from 'react';

const STORAGE_KEY = 'uploadJobId';
const TTL_MS = 2 * 60 * 60 * 1000; // 2 hours

function readStoredJob() {
    try {
        const raw = localStorage.getItem(STORAGE_KEY);
        if (!raw) return null;
        const { id, startedAt } = JSON.parse(raw);
        if (Date.now() - startedAt > TTL_MS) {
            localStorage.removeItem(STORAGE_KEY);
            return null;
        }
        return id;
    } catch {
        localStorage.removeItem(STORAGE_KEY);
        return null;
    }
}

/**
 * Manages upload job state and polling independently of the modal.
 * Polling continues even when the modal is closed so the user can receive
 * a background notification when ingestion finishes.
 */
export function useUploadJob() {
    const [jobId, setJobId] = useState(() => readStoredJob());
    const [status, setStatus] = useState(() => readStoredJob() ? 'processing' : 'idle');
    const [progress, setProgress] = useState(0);
    const [message, setMessage] = useState(() => readStoredJob() ? 'Checking upload progress...' : '');
    const [totalEvents, setTotalEvents] = useState(null);
    const pollRef = useRef(null);

    const startJob = useCallback((id) => {
        localStorage.setItem(STORAGE_KEY, JSON.stringify({ id, startedAt: Date.now() }));
        setJobId(id);
        setStatus('processing');
        setProgress(0);
        setMessage('Starting ingestion...');
        setTotalEvents(null);
    }, []);

    const resetJob = useCallback(() => {
        localStorage.removeItem(STORAGE_KEY);
        setJobId(null);
        setStatus('idle');
        setProgress(0);
        setMessage('');
        setTotalEvents(null);
    }, []);

    useEffect(() => {
        function onStorage(e) {
            if (e.key !== STORAGE_KEY && e.key !== null) return;
            if (!e.newValue) {
                clearInterval(pollRef.current);
                setJobId(null);
                setStatus('idle');
                setProgress(0);
                setMessage('');
                setTotalEvents(null);
            }
        }
        window.addEventListener('storage', onStorage);
        return () => window.removeEventListener('storage', onStorage);
    }, []);

    useEffect(() => {
        if (!jobId) return;

        pollRef.current = setInterval(async () => {
            try {
                const res = await fetch(`/api/upload/status/${jobId}`, { credentials: 'include' });
                if (!res.ok) {
                    if (res.status === 404) {
                        clearInterval(pollRef.current);
                        localStorage.removeItem(STORAGE_KEY);
                        setJobId(null);
                        setStatus('error');
                        setMessage('Upload session expired. Please try again.');
                    }
                    return;
                }
                const data = await res.json();

                setProgress(data.progress ?? 0);
                setMessage(data.message ?? '');

                if (data.status === 'complete') {
                    clearInterval(pollRef.current);
                    localStorage.removeItem(STORAGE_KEY);
                    setTotalEvents(data.total_events);
                    setJobId(null);
                    setStatus('complete');
                } else if (data.status === 'error') {
                    clearInterval(pollRef.current);
                    localStorage.removeItem(STORAGE_KEY);
                    setJobId(null);
                    setStatus('error');
                }
            } catch (err) {
                console.error('Upload status poll failed:', err);
            }
        }, 2000);

        return () => clearInterval(pollRef.current);
    }, [jobId]);

    return { status, progress, message, totalEvents, startJob, resetJob };
}
