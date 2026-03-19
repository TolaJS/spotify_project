import React, { useEffect } from 'react';
import { CheckCircle, AlertCircle, X } from 'lucide-react';
import { motion } from 'framer-motion';

function Toast({ message, type, onClose, duration = 6000 }) {
    useEffect(() => {
        const timer = setTimeout(onClose, duration);
        return () => clearTimeout(timer);
    }, [onClose, duration]);

    return (
        <motion.div
            initial={{ opacity: 0, x: 60 }}
            animate={{ opacity: 1, x: 0 }}
            exit={{ opacity: 0, x: 60 }}
            transition={{ type: 'spring', stiffness: 300, damping: 30 }}
            className={`flex items-start gap-3 px-4 py-3 rounded-xl shadow-2xl border w-80 ${
                type === 'success'
                    ? 'bg-zinc-900 border-spotify-green/40'
                    : 'bg-zinc-900 border-red-500/40'
            }`}
        >
            {type === 'success'
                ? <CheckCircle className="w-5 h-5 text-spotify-green flex-shrink-0 mt-0.5" />
                : <AlertCircle className="w-5 h-5 text-red-500 flex-shrink-0 mt-0.5" />
            }
            <p className="text-white text-sm flex-1 leading-relaxed">{message}</p>
            <button
                onClick={onClose}
                className="text-zinc-500 hover:text-white transition-colors flex-shrink-0"
            >
                <X className="w-4 h-4" />
            </button>
        </motion.div>
    );
}

export default Toast;
