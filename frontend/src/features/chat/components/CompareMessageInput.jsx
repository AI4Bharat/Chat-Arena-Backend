import { useState, useRef, useEffect } from 'react';
import { Send, Square } from 'lucide-react';
import { useDispatch } from 'react-redux';
import { toast } from 'react-hot-toast';
import { useSelector } from 'react-redux';
import { createSession } from '../store/chatSlice';
import { useStreamingMessageCompare } from '../hooks/useStreamingMessagesCompare';

export function CompareMessageInput({ sessionId, modelAId, modelBId }) {
  const { activeSession, messages, selectedMode, selectedModels } = useSelector((state) => state.chat);
  const [input, setInput] = useState('');
  const [isStreaming, setIsStreaming] = useState(false);
  const textareaRef = useRef(null);
  const dispatch = useDispatch();
  const [isCreatingSession, setIsCreatingSession] = useState(false);
  const { streamMessage } = useStreamingMessageCompare();

  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
      textareaRef.current.style.height = `${textareaRef.current.scrollHeight}px`;
    }
  }, [input]);

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!input.trim() || isStreaming || isCreatingSession) return;

    const content = input.trim();
    if (!activeSession) {
      // For random mode, no model validation needed
      if (selectedMode === 'compare' && (!selectedModels?.modelA || !selectedModels?.modelB)) {
        toast.error('Please select models first');
        return;
      }

      setIsCreatingSession(true);
      try {
        const result = await dispatch(createSession({
          mode: selectedMode,
          modelA: selectedModels?.modelA,
          modelB: selectedModels?.modelB,
        })).unwrap();
        setIsCreatingSession(false);

        setInput('');
        setIsStreaming(true);
        console.log('New session created with ID:', result.id);
        console.log(content)
        await streamMessage({sessionId:result.id, content:content, modelAId:result.model_a?.id || modelAId, modelBId:result.model_b?.id || modelBId, parentMessageIds:[]});
        setIsStreaming(false);

      } catch (error) {
        toast.error('Failed to create session');
        console.error('Session creation error:', error);
        setIsCreatingSession(false);
        setIsStreaming(false);
        return;
      }
    } else {
      // Existing session flow
      setInput('');
      const parentMessageIds = messages[activeSession.id]
        .filter(msg => msg.role === 'assistant')
        .slice(-2)
        .map(msg => msg.id);
      setIsStreaming(true);
      await streamMessage({sessionId, content, modelAId, modelBId, parentMessageIds});
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
    <div className="border-t border-gray-200 bg-white p-4">
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
  );
}