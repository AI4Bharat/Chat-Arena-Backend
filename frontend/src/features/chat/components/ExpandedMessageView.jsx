import { useEffect, useRef } from 'react';
import { X, Bot, Copy, RefreshCw } from 'lucide-react'; // Import new icons
import { motion, AnimatePresence } from 'framer-motion';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { toast } from 'react-hot-toast'; // Import toast for copy feedback

export function ExpandedMessageView({ message, modelName, onClose }) {
  const contentRef = useRef(null);
  // Auto-scroll logic, reused from MessageItem
  useEffect(() => {
    if (message?.isStreaming && contentRef.current) {
      const element = contentRef.current;
      element.scrollTop = element.scrollHeight;
    }
  }, [message?.content, message?.isStreaming]);

  // Handle Escape key to close the modal
  useEffect(() => {
    const handleKeyDown = (event) => {
      if (event.key === 'Escape') {
        onClose();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [onClose]);

  const handleCopy = () => {
    if (message?.content) {
      navigator.clipboard.writeText(message.content);
      toast.success('Copied to clipboard!');
    }
  };

  return (
    <AnimatePresence>
      {message && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          onClick={onClose}
          className="absolute inset-0 z-30 flex items-center justify-center bg-gray-400/20 backdrop-blur-sm"
        >
          <motion.div
            initial={{ opacity: 0, scale: 0.95 }}
            animate={{ opacity: 1, scale: 1 }}
            exit={{ opacity: 0, scale: 0.95 }}
            transition={{ duration: 0.2, ease: 'easeOut' }}
            className="m-8 bg-white rounded-lg shadow-2xl w-full max-h-[calc(100%-4.3rem)] flex flex-col border border-gray-200/80"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex justify-between items-center p-3 border-b border-gray-200 flex-shrink-0">
              <div className="flex items-center gap-2">
                <div className="w-6 h-6 flex items-center justify-center bg-gray-600 rounded-full">
                  <Bot size={14} className="text-white" />
                </div>
                <span className="font-medium text-sm text-gray-800">{modelName}</span>
              </div>
              <div className="flex items-center gap-2">
                <button
                  onClick={handleCopy}
                  className="p-1 rounded-full text-gray-500 hover:bg-gray-100"
                  aria-label="Copy"
                  title="Copy"
                >
                  <Copy size={18} />
                </button>
                <button
                  onClick={() => toast.error('--')}
                  className="p-1 rounded-full text-gray-500 hover:bg-gray-100"
                  aria-label="Regenerate"
                  title="Regenerate"
                >
                  <RefreshCw size={18} />
                </button>
                <button
                  onClick={onClose}
                  className="p-1 rounded-full text-gray-500 hover:bg-gray-100"
                  aria-label="Close"
                  title="Close"
                >
                  <X size={22} />
                </button>
              </div>
            </div>

            {/* Content */}
            <div ref={contentRef} className="flex-1 p-6 overflow-y-auto">
              <div className="prose prose-sm max-w-4xl mx-auto text-justify">
                <ReactMarkdown remarkPlugins={[remarkGfm]}>{message.content}</ReactMarkdown>
                {message.isStreaming && (
                  <span className="inline-block w-2 h-4 bg-gray-400 animate-pulse ml-1" />
                )}
              </div>
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}