import { useState, useRef, useEffect } from 'react';
import { Send, Paperclip, LoaderCircle, Info } from 'lucide-react';
import { useStreamingMessage } from '../hooks/useStreamingMessage';
import { useStreamingMessageCompare } from '../hooks/useStreamingMessagesCompare';
import { toast } from 'react-hot-toast';
import { useGuestLimitations } from '../hooks/useGuestLimitations';
import { AuthModal } from '../../auth/components/AuthModal';
import { useSelector, useDispatch } from 'react-redux';
import { createSession } from '../store/chatSlice';
import { useNavigate } from 'react-router-dom';

export function MessageInput({ sessionId, modelAId, modelBId, isCentered = false, isLocked = false }) {
  const dispatch = useDispatch();
  const navigate = useNavigate();
  const { activeSession, messages, selectedMode, selectedModels } = useSelector((state) => state.chat);
  const [input, setInput] = useState('');
  const [isStreaming, setIsStreaming] = useState(false);
  const [isCreatingSession, setIsCreatingSession] = useState(false);
  const textareaRef = useRef(null);
  const { streamMessage } = useStreamingMessage();
  const { streamMessageCompare } = useStreamingMessageCompare();
  const { checkMessageLimit, showAuthPrompt, setShowAuthPrompt } = useGuestLimitations();

  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
      const scrollHeight = textareaRef.current.scrollHeight;
      textareaRef.current.style.height = `${scrollHeight}px`;
    }
  }, [input]);

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!input.trim() || isStreaming || isCreatingSession || isLocked) return;

    if (!checkMessageLimit()) {
      return;
    }

    const content = input.trim();

    if (!activeSession) {
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

        setInput('');
        setIsStreaming(true);

        if (selectedMode === 'direct') {
          await streamMessage({ sessionId: result.id, content, modelId: result.model_a?.id, parent_message_ids: [] });
        } else {
          await streamMessageCompare({ sessionId: result.id, content, modelAId: result.model_a?.id, modelBId: result.model_b?.id, parentMessageIds: [] });
        }
      } catch (error) {
        toast.error('Failed to create session');
        console.error('Session creation error:', error);
      } finally {
        setIsCreatingSession(false);
        setIsStreaming(false);
      }
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

  const isLoading = isStreaming || isCreatingSession;

  const formMaxWidth = isCentered ? 'max-w-3xl' : (activeSession ? activeSession?.mode === "direct" ? 'max-w-3xl' : 'max-w-7xl' : selectedMode === "direct" ? 'max-w-3xl' : 'max-w-7xl');

  if (isLocked) {
    return (
      <div className={`w-full px-2 sm:px-4 ${isCentered ? 'pb-0' : 'pb-2 sm:pb-4'} bg-transparent`}>
        <div className={`${formMaxWidth} mx-auto`}>
          <div className="flex items-center justify-center gap-2 text-center bg-yellow-50 border border-yellow-200 text-yellow-800 text-sm rounded-lg p-3">
            <Info size={16} />
            Feedback submitted. Please start a new chat to continue.
          </div>
        </div>
      </div>
    );
  }


  return (
    <>
      <div className={`w-full px-2 sm:px-4 ${isCentered ? 'pb-0' : 'pb-2 sm:pb-4'} bg-transparent`}>
        <form onSubmit={handleSubmit} className={`${formMaxWidth} mx-auto`}>
          <div
            className="flex flex-col bg-white border-2 border-orange-500 rounded-xl shadow-sm transition-shadow transition-colors duration-300"
          >
            <textarea
              ref={textareaRef}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder={isCentered ? 'Ask anything...' : 'Ask followup...'}
              className={`w-full px-3 sm:px-4 pt-3 sm:pt-4 bg-transparent border-none focus:ring-0 focus:outline-none resize-none text-gray-800 placeholder:text-gray-500 transition-colors duration-300 text-sm sm:text-base
                   ${isCentered ? 'max-h-96' : 'max-h-32'}
                   [&::-webkit-scrollbar]:w-1.5
                   [&::-webkit-scrollbar-track]:bg-transparent
                   [&::-webkit-scrollbar-thumb]:rounded-full
                   [&::-webkit-scrollbar-thumb]:bg-gray-300
                   hover:[&::-webkit-scrollbar-thumb]:bg-gray-400`}
              rows="1"
            />
            <div className="flex items-center justify-between p-2">
              <div className="flex items-center">
                <button
                  type="button"
                  onClick={() => toast('Image upload coming soon!')}
                  className="p-1.5 sm:p-2 text-gray-500 rounded-md hover:bg-gray-100 hover:text-orange-600 transition-colors disabled:opacity-50"
                  disabled={isLoading}
                  aria-label="Attach file"
                >
                  <Paperclip size={18} className="sm:w-5 sm:h-5" />
                </button>
              </div>

              <button
                type="submit"
                disabled={!input.trim() || isLoading}
                className="w-8 h-8 sm:w-9 sm:h-9 flex items-center justify-center bg-orange-500 text-white rounded-lg hover:bg-orange-700 transition-colors disabled:bg-gray-400 disabled:cursor-not-allowed"
                aria-label="Send message"
              >
                {isLoading ? (
                  <LoaderCircle size={18} className="animate-spin sm:w-5 sm:h-5" />
                ) : (
                  <Send size={18} className="sm:w-5 sm:h-5" />
                )}
              </button>
            </div>
          </div>
        </form>
      </div>


      <AuthModal isOpen={showAuthPrompt} onClose={() => setShowAuthPrompt(false)} />
    </>
  );
}