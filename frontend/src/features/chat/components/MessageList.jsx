import { useEffect, useRef, useState } from 'react';
import { MessageItem } from './MessageItem';

export function MessageList({ messages, streamingMessages, session, onExpand }) {
  const endOfMessagesRef = useRef(null);
  const mainScrollRef = useRef(null);
  const [isUserScrolledUp, setIsUserScrolledUp] = useState(false);
  useEffect(() => {
    if (!isUserScrolledUp) {
      endOfMessagesRef.current?.scrollIntoView({ behavior: 'smooth' });
    }
  }, [messages, streamingMessages, isUserScrolledUp]);

  const handleMainScroll = () => {
    const el = mainScrollRef.current;
    if (el) {
      const isAtBottom = el.scrollHeight - el.scrollTop <= el.clientHeight + 50;
      setIsUserScrolledUp(!isAtBottom);
    }
  };

  return (
    <div
      ref={mainScrollRef}
      onScroll={handleMainScroll}
      className="flex-1 overflow-y-auto p-2 sm:p-4 relative scroll-gutter-stable"
    >
      <div className="max-w-3xl mx-auto space-y-3 sm:space-y-4">
        {messages.map((message) => (
          <MessageItem
            key={message.id}
            message={message}
            viewMode='single'
            modelName={session.model_a?.display_name}
            onExpand={onExpand}
          />
        ))}

        {Object.entries(streamingMessages).map(([messageId, streamingData]) => (
          <MessageItem
            key={messageId}
            message={{
              id: messageId,
              content: streamingData.content,
              role: 'assistant',
              isStreaming: true,
            }}
            viewMode='single'
            modelName={session.model_a?.display_name}
          />
        ))}

        <div ref={endOfMessagesRef} />
      </div>
    </div>
  );
}