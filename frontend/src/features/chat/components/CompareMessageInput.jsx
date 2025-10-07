import { useState, useRef, useEffect } from 'react';
import { Send, Square } from 'lucide-react';
import { useDispatch } from 'react-redux';
import { apiClient } from '../../../shared/api/client';
import { endpoints } from '../../../shared/api/endpoints';
import { addMessage, updateStreamingMessage } from '../store/chatSlice';
import { v4 as uuidv4 } from 'uuid';
import { toast } from 'react-hot-toast';
import { useSelector } from 'react-redux';

export function CompareMessageInput({ sessionId, modelAId, modelBId, onMessageSent }) {
  const { activeSession, messages } = useSelector((state) => state.chat);
  const [input, setInput] = useState('');
  const [isStreaming, setIsStreaming] = useState(false);
  const textareaRef = useRef(null);
  const dispatch = useDispatch();

  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
      textareaRef.current.style.height = `${textareaRef.current.scrollHeight}px`;
    }
  }, [input]);

  const unescapeChunk = (chunk) => chunk.replace(/\\\\/g, '\\').replace(/\\n/g, '\n');

  const streamComparison = async (content, parent_message_ids = []) => {
    const userMessageId = uuidv4();
    const aiMessageIdA = uuidv4();
    const aiMessageIdB = uuidv4();

    const userMessage = {
      id: userMessageId,
      role: 'user',
      content,
      parent_message_ids,
      status: 'pending',
    };

    const aiMessageA = {
      id: aiMessageIdA,
      role: 'assistant',
      content: '',
      parent_message_ids: [userMessageId],
      modelId: modelAId,
      status: 'pending',
      participant: 'a',
    };

    const aiMessageB = {
      id: aiMessageIdB,
      role: 'assistant',
      content: '',
      parent_message_ids: [userMessageId],
      modelId: modelBId,
      status: 'pending',
      participant: 'b',
    };

    dispatch(addMessage({ sessionId, message: userMessage }));
    dispatch(updateStreamingMessage({ sessionId, messageId: aiMessageIdA, chunk: "", isComplete: false, participant: 'a', }));
    dispatch(updateStreamingMessage({ sessionId, messageId: aiMessageIdB, chunk: "", isComplete: false, participant: 'b', }));
    setIsStreaming(true);

    try {
      const response = await fetch(`${apiClient.defaults.baseURL}${endpoints.messages.stream}`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${localStorage.getItem('access_token')}`,
        },
        body: JSON.stringify({
          session_id: sessionId,
          messages: [userMessage, aiMessageA, aiMessageB],
        }),
      });

      if (!response.ok) throw new Error('Stream request failed');

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';

      const modelStatus = {
        a: { complete: false, error: null },
        b: { complete: false, error: null }
      };

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';

        for (const line of lines) {
          if (!line.trim()) continue;

          if (line.startsWith('a0:')) {
            const content = line.slice(4, -1);
            dispatch(updateStreamingMessage({
              sessionId,
              messageId: aiMessageIdA,
              chunk: unescapeChunk(content),
              isComplete: false,
              participant: 'a',
            }));
          }

          else if (line.startsWith('b0:')) {
            const content = line.slice(4, -1);
            dispatch(updateStreamingMessage({
              sessionId,
              messageId: aiMessageIdB,
              chunk: unescapeChunk(content),
              isComplete: false,
              participant: 'b',
            }));
          }

          else if (line.startsWith('ad:')) {
            try {
              const data = JSON.parse(line.slice(3));

              if (data.finishReason === 'stop') {
                modelStatus.a.complete = true;
                dispatch(updateStreamingMessage({
                  sessionId,
                  messageId: aiMessageIdA,
                  chunk: '',
                  isComplete: true,
                  participant: 'a',
                }));
              } else if (data.finishReason === 'error') {
                modelStatus.a.complete = true;
                modelStatus.a.error = data.error;
                toast.error(`Model A error: ${data.error}`);

                // dispatch(updateStreamingMessage({
                //   sessionId,
                //   messageId: aiMessageIdA,
                //   chunk: '\n\n[Error occurred while generating response]',
                //   isComplete: true,
                //   participant: 'a',
                //   error: true,
                // }));
              }
            } catch (e) {
              console.error('Failed to parse model A done signal:', e);
            }
          }

          else if (line.startsWith('bd:')) {
            try {
              const data = JSON.parse(line.slice(3));

              if (data.finishReason === 'stop') {
                modelStatus.b.complete = true;
                dispatch(updateStreamingMessage({
                  sessionId,
                  messageId: aiMessageIdB,
                  chunk: '',
                  isComplete: true,
                  participant: 'b',
                }));
              } else if (data.finishReason === 'error') {
                modelStatus.b.complete = true;
                modelStatus.b.error = data.error;
                toast.error(`Model B error: ${data.error}`);

                // Mark as complete with error
                // dispatch(updateStreamingMessage({
                //   sessionId,
                //   messageId: aiMessageIdB,
                //   chunk: '\n\n[Error occurred while generating response]',
                //   isComplete: true,
                //   participant: 'b',
                //   error: true,
                // }));
              }
            } catch (e) {
              console.error('Failed to parse model B done signal:', e);
            }
          }
        }

        if (modelStatus.a.complete && modelStatus.b.complete) {
          break;
        }
      }

      if (onMessageSent) {
        onMessageSent();
      }

    } catch (error) {
      console.error('Streaming comparison error:', error);
      toast.error('Failed to send message to both models');

      // // Mark both as complete on error
      // dispatch(updateStreamingMessage({
      //   sessionId,
      //   messageId: aiMessageIdA,
      //   chunk: '',
      //   isComplete: true,
      //   participant: 'a',
      //   error: true,
      // }));
      // dispatch(updateStreamingMessage({
      //   sessionId,
      //   messageId: aiMessageIdB,
      //   chunk: '',
      //   isComplete: true,
      //   participant: 'b',
      //   error: true,
      // }));
    } finally {
      setIsStreaming(false);
    }
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!input.trim() || isStreaming) return;

    const content = input.trim();
    setInput('');
    const parentMessageIds = messages[activeSession.id]
    .filter(msg => msg.role === 'assistant')
    .slice(-2)
    .map(msg => msg.id);
    await streamComparison(content, parentMessageIds);
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
            disabled={isStreaming}
          />

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
  );
}