import { useState, useRef, useEffect, use } from 'react';
import { Send, Paperclip, Square } from 'lucide-react';
import { useStreamingMessage } from '../hooks/useStreamingMessage';
import { toast } from 'react-hot-toast';
import { useGuestLimitations } from '../hooks/useGuestLimitations';
import { AuthModal } from '../../auth/components/AuthModal';
import { useSelector } from 'react-redux';

export function MessageInput({ sessionId, modelId }) {
  const { activeSession, messages } = useSelector((state) => state.chat);
  const sessionMessages = messages[activeSession.id] || [];
  const [input, setInput] = useState('');
  const [isStreaming, setIsStreaming] = useState(false);
  const [lastMessageId, setLastMessageId] = useState([]);
  const textareaRef = useRef(null);
  const { streamMessage } = useStreamingMessage();
  const { 
    checkMessageLimit, 
    incrementMessageCount, 
    showAuthPrompt,
    setShowAuthPrompt,
    messageCount,
    messageLimit,
    isGuest
  } = useGuestLimitations();

  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
      textareaRef.current.style.height = `${textareaRef.current.scrollHeight}px`;
    }
  }, [input]);

  useEffect(() => {
    if (sessionMessages.length !== 0){
      setLastMessageId([sessionMessages[sessionMessages.length - 1].id]);
    }
  }, [sessionMessages]);

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!input.trim() || isStreaming || !modelId) return;

    // Check guest limitations
    if (!checkMessageLimit()) {
      return;
    }

    const content = input.trim();
    setInput('');
    setIsStreaming(true);
    incrementMessageCount();

    try {
      await streamMessage({
        sessionId,
        content,
        modelId,
        parent_message_ids:lastMessageId,
      });
    } catch (error) {
      toast.error('Failed to send message');
    } finally {
      setIsStreaming(false);
    }
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSubmit(e);
    }
  };

  return (
    <>
      <div className="border-t border-gray-200 bg-white p-4">
        {/* Guest limit indicator */}
        {/* {isGuest && (
          <div className="max-w-3xl mx-auto mb-2">
            <div className="flex items-center justify-between text-sm text-gray-500">
              <span>Guest messages: {messageCount}/{messageLimit}</span>
              <button
                onClick={() => setShowAuthPrompt(true)}
                className="text-orange-600 hover:underline"
              >
                Sign in for unlimited
              </button>
            </div>
          </div>
        )} */}

        <form onSubmit={handleSubmit} className="max-w-3xl mx-auto">
          <div className="flex items-end gap-2">
            <button
              type="button"
              className="p-2 text-gray-500 hover:text-gray-700 rounded-lg hover:bg-gray-100"
            >
              <Paperclip size={20} />
            </button>
            
            <div className="flex-1 relative">
              <textarea
                ref={textareaRef}
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder="Type your message..."
                className="w-full px-4 py-2 pr-12 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-orange-500 resize-none max-h-32"
                rows="1"
                disabled={isStreaming}
              />
            </div>
            
            <button
              type="submit"
              disabled={!input.trim() || isStreaming}
              className="p-2 bg-orange-600 text-white rounded-lg hover:bg-orange-700 disabled:bg-gray-300 disabled:cursor-not-allowed"
            >
              {isStreaming ? <Square size={20} /> : <Send size={20} />}
            </button>
          </div>
        </form>
      </div>

      {/* Auth Modal */}
      <AuthModal isOpen={showAuthPrompt} onClose={() => setShowAuthPrompt(false)} />
    </>
  );
}