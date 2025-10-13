import { User, Bot, Copy, RefreshCw, GitBranch, Expand } from 'lucide-react';
import { useState, useEffect, useRef } from 'react';
import { toast } from 'react-hot-toast';
import ReactMarkdown from "react-markdown";
import remarkGfm from 'remark-gfm';
import clsx from 'clsx';

export function MessageItem({ message, onExpand, viewMode = 'single', modelName = 'Random', feedbackState = null, previewState = null }) {
  const [copied, setCopied] = useState(false);
  const isUser = message.role === 'user';
  const contentRef = useRef(null);

  const [isUserScrolledUp, setIsUserScrolledUp] = useState(false);
  const [scrollState, setScrollState] = useState({ canScrollUp: false, canScrollDown: false });

  useEffect(() => {
    handleScroll();
  }, [message.content]);

  const handleScroll = () => {
    const el = contentRef.current;
    if (!el) return;
    const canScrollUp = el.scrollTop > 0;
    const canScrollDown = el.scrollHeight > el.clientHeight && el.scrollHeight - el.scrollTop > el.clientHeight + 2;
    setScrollState({ canScrollUp, canScrollDown });
  };

  useEffect(() => {
    if (contentRef.current && message.isStreaming && !isUserScrolledUp) {
      const element = contentRef.current;
      element.scrollTop = element.scrollHeight;
    }
  }, [message.content, message.isStreaming, isUserScrolledUp]);

  const handleCopy = () => {
    navigator.clipboard.writeText(message.content);
    setCopied(true);
    toast.success('Copied to clipboard');
    setTimeout(() => setCopied(false), 2000);
  };

  if (isUser) {
    return (
      <div className="flex justify-end my-4">
        <div className="group flex items-start gap-3 justify-end">
          <div className="bg-orange-500 text-white px-3 py-2 rounded-lg max-w-2xl">
            <p>{message.content}</p>
          </div>
        </div>
      </div>
    );
  }

  const renderActionIcons = () => (
    <div className="flex items-center gap-2 text-gray-500">
      <button onClick={handleCopy} className="p-1 hover:bg-gray-100 rounded" title="Copy">
        <Copy size={16} />
      </button>
      <button className="p-1 hover:bg-gray-100 rounded" title="Regenerate">
        <RefreshCw size={16} />
      </button>
      {/* <button className="p-1 hover:bg-gray-100 rounded" title="Branch">
        <GitBranch size={16} />
      </button> */}
      <button onClick={() => onExpand(message)} className="p-1 hover:bg-gray-100 rounded" title="Expand">
        <Expand size={16} />
      </button>
    </div>
  );

  const cardContainerClasses = viewMode === 'compare' ? 'w-full h-full flex flex-col' : 'w-full flex flex-col';
  const scrollableContentClasses = viewMode === 'compare' ? 'p-4 flex-1 max-h-[65vh] overflow-y-auto' : 'p-4 flex-1';

  const activeState = feedbackState || previewState;

  const cardClasses = clsx(
    'rounded-lg bg-white w-full flex flex-col',
    { 'h-full': viewMode === 'compare' },
    'border border-gray-200',
    {
      'outline outline-2': activeState,
      'outline-green-500': activeState === 'winner',
      'outline-red-500': activeState === 'loser',
    },
    {
      'animate-border-glow': previewState && !feedbackState,
      'glow-winner': previewState === 'winner',
      'glow-loser': previewState === 'loser',
    }
  );

  return (
    <div className={cardClasses}>
      <div className="flex justify-between items-center p-2 border-b border-gray-200 flex-shrink-0">
        <div className="flex items-center gap-2">
          <div className="w-6 h-6 flex items-center justify-center bg-gray-600 rounded-full">
            <Bot size={14} className="text-white" />
          </div>
          <span className={clsx("font-medium text-sm", {'text-green-500': feedbackState === 'winner' || previewState === 'winner','text-red-500': feedbackState === 'loser' || previewState === 'loser'})}>{modelName}</span>
        </div>
        {!message.isStreaming && message.content && renderActionIcons()}
      </div>

      <div ref={contentRef} onScroll={handleScroll} className={clsx('p-4 flex-1 scroll-fade scrollbar-hide', {'max-h-[65vh] overflow-y-auto': viewMode === 'compare','overflow-y-auto': viewMode === 'single'})}>
        <div className="prose prose-sm max-w-none text-gray-900">
          <ReactMarkdown remarkPlugins={[remarkGfm]}>{message.content}</ReactMarkdown>
          {message.isStreaming && <span className="inline-block w-2 h-4 bg-gray-400 animate-pulse ml-1" />}
        </div>
      </div>
    </div>
  );
}