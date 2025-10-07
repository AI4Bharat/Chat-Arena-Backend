import { useEffect, useState } from 'react';
import { MessageList } from './MessageList';
import { MessageInput } from './MessageInput';
import { ThumbsUp } from 'lucide-react';
import { apiClient } from '../../../shared/api/client';
import { endpoints } from '../../../shared/api/endpoints';
import { toast } from 'react-hot-toast';
import { CompareMessageInput } from './CompareMessageInput';

export function CompareView({ session, messages, streamingMessages }) {
  const [showFeedback, setShowFeedback] = useState(false);
  const [lastMessagePair, setLastMessagePair] = useState(null);

  const handlePreference = async (preference) => {
    try {
      const messageId = messages.filter(msg => msg.role === 'user').slice(-1)[0]?.id;
      let preferredModelId = null;
      if (preference === 'model_a') {
        preferredModelId = session.model_a.id;
      } else if (preference === 'model_b') {
        preferredModelId = session.model_b.id;
      } else if (preference === 'tie') {
        preferredModelId = [session.model_a.id, session.model_b.id];
      }
      await apiClient.post(endpoints.feedback.submit, {
        session_id: session.id,
        feedback_type: 'preference',
        message_id: messageId,
        preferred_model_id: preferredModelId,
      });
      toast.success('Preference recorded');
      setShowFeedback(false);
    } catch (error) {
      toast.error('Failed to submit preference');
    }
  };

  // Split messages for each model
  const modelAMessages = messages.filter((msg, idx) => 
    msg.role === 'user' || (msg.role === 'assistant' && msg.participant === 'a')
  );
  const modelBMessages = messages.filter((msg, idx) => 
    msg.role === 'user' || (msg.role === 'assistant' && msg.participant === 'b')
  );

  const streamingMessagesA = Object.fromEntries(
    Object.entries(streamingMessages).filter(([_, msg]) => msg.participant === 'a')
  );
  
  const streamingMessagesB = Object.fromEntries(
    Object.entries(streamingMessages).filter(([_, msg]) => msg.participant === 'b')
  );

  return (
    <div className="flex-1 flex flex-col overflow-hidden min-h-0">
      {/* Compare Header */}
      <div className="bg-white border-b border-gray-200 p-4 flex-shrink-0">
        <div className="max-w-6xl mx-auto flex items-center justify-around">
          <div className="flex items-center gap-4">
            <div className="text-sm">
              <span className="font-medium">Model A:</span> {session.model_a?.provider || 'Random'}
            </div>
            <div className="text-gray-400">vs</div>
            <div className="text-sm">
              <span className="font-medium">Model B:</span> {session.model_b?.provider || 'Random'}
            </div>
          </div>
          {showFeedback && (
            <div className="flex items-center gap-2">
              <span className="text-sm text-gray-600">Which response was better?</span>
              <button
                onClick={() => handlePreference('model_a')}
                className="px-3 py-1 bg-orange-100 text-orange-700 rounded-lg hover:bg-orange-200"
              >
                Model A
              </button>
              <button
                onClick={() => handlePreference('model_b')}
                className="px-3 py-1 bg-green-100 text-green-700 rounded-lg hover:bg-green-200"
              >
                Model B
              </button>
              <button
                onClick={() => handlePreference('tie')}
                className="px-3 py-1 bg-gray-100 text-gray-700 rounded-lg hover:bg-gray-200"
              >
                Tie
              </button>
              <button
                onClick={() => handlePreference('both bad')}
                className="px-3 py-1 bg-gray-100 text-gray-700 rounded-lg hover:bg-gray-200"
              >
                Both Bad
              </button>
            </div>
          )}
        </div>
      </div>

      {/* Side by side message lists */}
      <div className="flex-1 flex overflow-hidden min-h-0">
        <div className="flex-1 border-r border-gray-400 flex flex-col">
          <MessageList
            messages={modelAMessages}
            streamingMessages={streamingMessagesA}
            sessionId={session.id}
          />
        </div>
        <div className="flex-1 flex flex-col">
          <MessageList
            messages={modelBMessages}
            streamingMessages={streamingMessagesB}
            sessionId={session.id}
          />
        </div>
      </div>

      {/* Shared Input */}
      <div className="flex-shrink-0">
        <CompareMessageInput
          sessionId={session.id} 
          modelAId={session.model_a?.id}
          modelBId={session.model_b?.id}
          onMessageSent={() => setShowFeedback(true)}
        />
      </div>
    </div>
  );
}