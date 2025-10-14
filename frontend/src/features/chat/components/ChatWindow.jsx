import { useSelector } from 'react-redux';
import { MessageList } from './MessageList';
import { MessageInput } from './MessageInput';
import { CompareView } from './CompareView';
import { EmptyChat } from './EmptyChat';
import { useEffect, useState } from 'react';
import { ExpandedMessageView } from './ExpandedMessageView';

export function ChatWindow() {
  const { activeSession, messages, streamingMessages, selectedMode } = useSelector((state) => state.chat);
  const [expandedMessage, setExpandedMessage] = useState(null);

  const sessionMessages = messages[activeSession?.id] || [];
  const sessionStreamingMessages = streamingMessages[activeSession?.id] || {};

  const shouldShowCompareView = activeSession && (activeSession?.mode === 'compare' || activeSession?.mode === 'random');
  const isNewRandomChat = !activeSession && (selectedMode === 'compare' || selectedMode === 'random');
  
  const handleExpand = (message) => {
    setExpandedMessage(message);
  };

  const handleCloseExpand = () => {
    setExpandedMessage(null);
  };

  let messageDataForModal = expandedMessage;

  return (
    <>
      <div className="flex-1 flex flex-col overflow-hidden min-h-0 bg-gray-50 relative">
        {(shouldShowCompareView || isNewRandomChat) ?
          <CompareView
            session={activeSession}
            messages={sessionMessages}
            streamingMessages={sessionStreamingMessages}
          /> :
          <>
            <ExpandedMessageView
              message={messageDataForModal}
              modelName={activeSession?.model_a?.display_name}
              onClose={handleCloseExpand}
            />
            <MessageList
              messages={sessionMessages}
              streamingMessages={sessionStreamingMessages}
              session={activeSession}
              onExpand={handleExpand}
            />
          </>
        }
        <div className="flex-shrink-0">
          <MessageInput
            sessionId={activeSession?.id}
            modelAId={activeSession?.model_a?.id}
            modelBId={activeSession?.model_b?.id}
          />
        </div>
      </div>
    </>
  );
}