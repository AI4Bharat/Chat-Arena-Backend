import { useSelector } from 'react-redux';
import { motion } from 'framer-motion';
import { MessageList } from './MessageList';
import { MessageInput } from './MessageInput';
import { CompareView } from './CompareView';
import { ExpandedMessageView } from './ExpandedMessageView';
import { NewChatLanding } from './NewChatLanding';
import { useState } from 'react';

export function ChatWindow() {
  const { activeSession, messages, streamingMessages } = useSelector((state) => state.chat);
  const [expandedMessage, setExpandedMessage] = useState(null);

  const sessionMessages = messages[activeSession?.id] || [];
  const sessionStreamingMessages = streamingMessages[activeSession?.id] || {};

  const handleExpand = (message) => setExpandedMessage(message);
  const handleCloseExpand = () => setExpandedMessage(null);

  return (
    <>
      <div className="flex-1 flex flex-col overflow-hidden min-h-0 bg-gray-50 relative">
        {!activeSession ? (
          <div className="h-full flex flex-col justify-center items-center">
            <NewChatLanding />
            <motion.div
              layoutId="message-input-wrapper"
              className="w-full"
            >
              <MessageInput isCentered={true} />
            </motion.div>
          </div>
        ) : (
          <>
            <div className="flex-1 overflow-y-auto">
              {activeSession.mode === 'compare' || activeSession.mode === 'random' ? (
                <CompareView
                  session={activeSession}
                  messages={sessionMessages}
                  streamingMessages={sessionStreamingMessages}
                />
              ) : (
                <MessageList
                  messages={sessionMessages}
                  streamingMessages={sessionStreamingMessages}
                  session={activeSession}
                  onExpand={handleExpand}
                />
              )}
            </div>
            <motion.div
              layoutId="message-input-wrapper"
              className="w-full flex-shrink-0"
            >
              <MessageInput
                isCentered={false}
                sessionId={activeSession?.id}
                modelAId={activeSession?.model_a?.id}
                modelBId={activeSession?.model_b?.id}
              />
            </motion.div>
          </>
        )}
      </div>

      <ExpandedMessageView
        message={expandedMessage}
        modelName={activeSession?.model_a?.display_name}
        onClose={handleCloseExpand}
      />
    </>
  );
}