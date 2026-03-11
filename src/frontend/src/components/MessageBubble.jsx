import React, { useState, useEffect } from 'react';
import ReactMarkdown from 'react-markdown';
import { motion, AnimatePresence } from 'framer-motion';
import { User, Bot } from 'lucide-react';
import RichMediaCard from './RichMediaCard';


function MessageBubble({ message }) {
    const isUser = message.sender === 'user';
    const isSystem = message.sender === 'system';

    const bubbleVariants = {
        hidden: { opacity: 0, y: 10, scale: 0.95 },
        visible: { opacity: 1, y: 0, scale: 1, transition: { duration: 0.3, ease: 'easeOut' } },
        exit: { opacity: 0, scale: 0.95, transition: { duration: 0.2, ease: 'easeIn' } }
    };

    // Used for cancelled/system inline text
    const textVariants = {
        hidden: { opacity: 0, y: 5 },
        visible: { opacity: 1, y: 0, transition: { duration: 0.4, ease: 'easeOut' } }
    };

    // Stagger container: each child animates 80ms after the previous
    const staggerContainerVariants = {
        hidden: {},
        visible: { transition: { staggerChildren: 0.08 } }
    };

    // Applied to each paragraph, list item, heading, etc.
    const staggerLineVariants = {
        hidden: { opacity: 0, y: 10 },
        visible: { opacity: 1, y: 0, transition: { duration: 0.35, ease: 'easeOut' } }
    };

    // Custom ReactMarkdown renderers — each block element is a motion child
    const markdownComponents = {
        p:    ({ children }) => <motion.p   variants={staggerLineVariants} className="mb-4 last:mb-0 leading-relaxed">{children}</motion.p>,
        li:   ({ children }) => <motion.li  variants={staggerLineVariants} className="mb-2">{children}</motion.li>,
        ul:   ({ children }) => <motion.ul  variants={staggerLineVariants} className="mb-4 last:mb-0 pl-5 list-disc space-y-1">{children}</motion.ul>,
        ol:   ({ children }) => <motion.ol  variants={staggerLineVariants} className="mb-4 last:mb-0 pl-5 list-decimal space-y-1">{children}</motion.ol>,
        h1:   ({ children }) => <motion.h1  variants={staggerLineVariants} className="mb-3 mt-2">{children}</motion.h1>,
        h2:   ({ children }) => <motion.h2  variants={staggerLineVariants} className="mb-3 mt-2">{children}</motion.h2>,
        h3:   ({ children }) => <motion.h3  variants={staggerLineVariants} className="mb-2 mt-2">{children}</motion.h3>,
        pre:  ({ children }) => <motion.pre variants={staggerLineVariants} className="mb-4 last:mb-0">{children}</motion.pre>,
    };

    if (isSystem) {
        if (message.isCancelledInfo) {
            return (
                <motion.div variants={bubbleVariants} initial="hidden" animate="visible" exit="exit" className="flex items-start w-full max-w-3xl mr-auto mb-6">
                    <div className="relative w-8 h-8 flex items-center justify-center shrink-0 mr-3 mt-1">
                        <div className="w-full h-full rounded-full bg-spotify-dark flex items-center justify-center shadow-sm border border-white/5 opacity-60">
                            <Bot className="w-4 h-4 text-zinc-500" />
                        </div>
                    </div>
                    <div className="flex flex-col items-start max-w-[85%] md:max-w-[80%] pt-2">
                        <motion.span 
                            variants={textVariants}
                            initial="hidden"
                            animate="visible"
                            className="text-sm italic text-zinc-500 font-medium"
                        >
                            {message.text}
                        </motion.span>
                    </div>
                </motion.div>
            );
        }

        return (
            <motion.div variants={bubbleVariants} initial="hidden" animate="visible" exit="exit" className="flex justify-center my-4">
                <div className="bg-red-900/30 border border-red-500/30 text-red-300 px-4 py-2 rounded-xl text-sm max-w-lg text-center shadow-sm">
                    {message.text}
                </div>
            </motion.div>
        );
    }

    if (!isUser) {
        return (
            <motion.div variants={bubbleVariants} initial="hidden" animate="visible" exit="exit" className="flex items-start w-full max-w-3xl mr-auto mb-6">
                
                {/* The Bot Avatar Area */}
                <div className="relative w-8 h-8 flex items-center justify-center shrink-0 mr-3 mt-1">
                    <AnimatePresence>
                        {message.isStatus && (
                            <motion.div
                                initial={{ opacity: 0 }}
                                animate={{ opacity: 1 }}
                                exit={{ opacity: 0, transition: { duration: 1, ease: 'easeOut' } }}
                                className="absolute inset-0 rounded-full border-2 border-transparent border-t-spotify-green animate-spin"
                            />
                        )}
                    </AnimatePresence>
                    <div className="w-full h-full rounded-full bg-spotify-dark flex items-center justify-center shadow-sm border border-white/5">
                        <Bot className={`w-4 h-4 text-spotify-green transition-opacity duration-1000 ${message.isStatus ? 'opacity-50' : 'opacity-100'}`} />
                    </div>
                </div>

                {/* The Content Area — flex-1 so it fills the row, pr-11 mirrors the user avatar width+margin */}
                <div className="flex flex-col items-start flex-1 pr-11">
                    
                    {message.isStatus ? (
                        <div className="text-zinc-400 py-1 flex items-center h-[32px]">
                            <span className="text-sm font-medium italic"></span> 
                        </div>
                    ) : (
                        <motion.div
                            variants={staggerContainerVariants}
                            initial="hidden"
                            animate="visible"
                            className="text-zinc-200 py-1 prose prose-invert prose-p:leading-relaxed prose-pre:bg-black/50 prose-a:text-spotify-green"
                        >
                            <ReactMarkdown components={markdownComponents}>{message.text}</ReactMarkdown>
                        </motion.div>
                    )}

                    {/* Rich Media Cards */}
                    {!message.isStatus && message.metadata?.rich_data && (
                        <motion.div 
                            initial={{ opacity: 0 }}
                            animate={{ opacity: 1 }}
                            transition={{ delay: 0.3 }}
                            className="mt-4 flex flex-wrap gap-2 w-full"
                        >
                            {message.metadata.rich_data.map((item, i) => (
                                <RichMediaCard key={i} item={item} />
                            ))}
                        </motion.div>
                    )}
                </div>
            </motion.div>
        );
    }

    // Normal User messages
    return (
        <motion.div 
            variants={bubbleVariants} 
            initial="hidden" 
            animate="visible" 
            exit="exit"
            className="flex w-full mb-6 justify-end"
        >
            <div className="flex flex-col items-end max-w-[85%] md:max-w-[80%]">
                <div className="px-5 py-3 bg-zinc-800 text-white rounded-2xl rounded-tr-sm border border-white/5 shadow-sm">
                    <span className="whitespace-pre-wrap leading-relaxed">{message.text}</span>
                </div>
            </div>
            <div className="w-8 h-8 rounded-full bg-spotify-green flex items-center justify-center shrink-0 ml-3 mt-1 shadow-sm">
                <User className="w-4 h-4 text-spotify-black" />
            </div>
        </motion.div>
    );
}

export default MessageBubble;