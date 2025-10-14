import { useState, useRef, useEffect } from 'react';
import { Send, Paperclip, Square } from 'lucide-react';
import { useStreamingMessage } from '../hooks/useStreamingMessage';
import { useStreamingMessageCompare } from '../hooks/useStreamingMessagesCompare';
import { toast } from 'react-hot-toast';
import { useGuestLimitations } from '../hooks/useGuestLimitations';
import { AuthModal } from '../../auth/components/AuthModal';
import { useSelector, useDispatch } from 'react-redux';
import { createSession } from '../store/chatSlice';
import { useNavigate } from 'react-router-dom';

export function MessageInput({ sessionId, modelAId, modelBId }) {
  const dispatch = useDispatch();
  const navigate = useNavigate();
  const { activeSession, messages, selectedMode, selectedModels } = useSelector((state) => state.chat);
  const sessionMessages = messages[activeSession?.id] || [];
  const [input, setInput] = useState('');
  const [isStreaming, setIsStreaming] = useState(false);
  const [isCreatingSession, setIsCreatingSession] = useState(false);
  const textareaRef = useRef(null);
  const { streamMessage } = useStreamingMessage();
  const { streamMessageCompare } = useStreamingMessageCompare();
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

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!input.trim() || isStreaming || isCreatingSession) return;

    // Check guest limitations
    if (!checkMessageLimit()) {
      return;
    }

    const content = input.trim();

    // If no active session, create one first
    if (!activeSession) {
      // Validate selections
      if (!selectedMode ||
        (selectedMode === 'direct' && !selectedModels?.modelA) ||
        (selectedMode === 'compare' && (!selectedModels?.modelA || !selectedModels?.modelB))) {
        toast.error('Please select a model first');
        return;
      }

      setIsCreatingSession(true);
      try {
        const result = await dispatch(createSession({
          mode: selectedMode,
          modelA: selectedModels.modelA,
          modelB: selectedModels.modelB,
        })).unwrap();

        navigate(`/chat/${result.id}`, { replace: true });

        // Session created successfully, now send the message
        setInput('');
        setIsStreaming(true);

        if (selectedMode === 'direct') {
          await streamMessage({ sessionId: result.id, content, modelId: result.model_a?.id || modelAId, parent_message_ids: [] });
        } else {
          await streamMessageCompare({ sessionId: result.id, content: content, modelAId: result.model_a?.id || modelAId, modelBId: result.model_b?.id || modelBId, parentMessageIds: [] });
        }
      } catch (error) {
        toast.error('Failed to create session');
        console.error('Session creation error:', error);
      } finally {
        setIsCreatingSession(false);
        setIsStreaming(false);
      }
      return;
    } else {
      setInput('');
      setIsStreaming(true);

      try {
        if (activeSession?.mode === 'direct') {
          const parentMessageIds = messages[activeSession.id].filter(msg => msg.role === 'assistant').slice(-1).map(msg => msg.id);
          await streamMessage({ sessionId, content, modelId: modelAId, parent_message_ids: parentMessageIds, });
        } else {
          const parentMessageIds = messages[activeSession.id].filter(msg => msg.role === 'assistant').slice(-2).map(msg => msg.id);
          await streamMessageCompare({ sessionId, content, modelAId, modelBId, parentMessageIds });
        }
      } catch (error) {
        toast.error('Failed to send message');
      } finally {
        setIsStreaming(false);
      }
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
            <textarea
              ref={textareaRef}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Type your message to compare responses..."
              className="flex-1 px-4 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-orange-500 resize-none max-h-32"
              rows="1"
              disabled={isStreaming || isCreatingSession}
            />

            <button
              type="submit"
              disabled={!input.trim() || isStreaming || isCreatingSession}
              className="p-2 bg-orange-600 text-white rounded-lg hover:bg-orange-700 disabled:bg-gray-300 disabled:cursor-not-allowed"
            >
              {(isStreaming || isCreatingSession) ? <Square size={20} /> : <Send size={20} />}
            </button>
          </div>
        </form>
      </div>

      {/* Auth Modal */}
      <AuthModal isOpen={showAuthPrompt} onClose={() => setShowAuthPrompt(false)} />
    </>
  );
}