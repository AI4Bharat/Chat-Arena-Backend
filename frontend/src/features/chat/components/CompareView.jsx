import { useEffect, useState, useRef, useMemo } from 'react';
import { apiClient } from '../../../shared/api/client';
import { endpoints } from '../../../shared/api/endpoints';
import { toast } from 'react-hot-toast';
import { ConversationTurn } from './ConversationTurn';
import { FeedbackSelector } from './FeedbackSelector';
import { ExpandedMessageView } from './ExpandedMessageView';
import { updateMessageFeedback } from '../store/chatSlice';
import { useDispatch } from 'react-redux';

export function CompareView({ session, messages, streamingMessages }) {
  const endOfMessagesRef = useRef(null);
  const [feedbackState, setFeedbackState] = useState({ turnId: null, selection: null });
  const [hoverPreview, setHoverPreview] = useState(null);
  const mainScrollRef = useRef(null);
  const [isUserScrolledUp, setIsUserScrolledUp] = useState(false);
  const [expandedMessage, setExpandedMessage] = useState(null);
  const dispatch = useDispatch();

  const handleExpand = (message) => {
    setExpandedMessage(message);
  };

  const handleCloseExpand = () => {
    setExpandedMessage(null);
  };

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

  const handlePreference = async (turnId, preference) => {
    setHoverPreview(null);
    setFeedbackState({ turnId, selection: preference });

    try {
      await apiClient.post(endpoints.feedback.submit, {
        session_id: session.id,
        feedback_type: 'preference',
        message_id: turnId,
        preference: preference,
      });
      dispatch(updateMessageFeedback({ sessionId: session.id, messageId: turnId, feedback: preference }));
      toast.success('Preference recorded!');
    } catch (error) {
      toast.error('Failed to submit preference.');
    }
  };

  const conversationTurns = useMemo(() => {
    const turns = [];

    // The core of the new logic: iterate through the presorted array.
    for (let i = 0; i < messages.length; i++) {
      if (messages[i].role === 'user') {
        const userMessage = messages[i];

        // The next two messages are the assistant responses.
        const potentialResponse1 = messages[i + 1];
        const potentialResponse2 = messages[i + 2];

        let modelAMessage = null;
        let modelBMessage = null;

        // Assign responses based on participant, regardless of their order.
        if (potentialResponse1 && potentialResponse1.role === 'assistant') {
          if (potentialResponse1.participant === 'a') modelAMessage = potentialResponse1;
          else modelBMessage = potentialResponse1;
        }
        if (potentialResponse2 && potentialResponse2.role === 'assistant') {
          if (potentialResponse2.participant === 'a') modelAMessage = potentialResponse2;
          else modelBMessage = potentialResponse2;
        }

        turns.push({ userMessage, modelAMessage, modelBMessage });

        // This is the key optimization: we've processed the user message and its two
        // potential responses, so we can skip the next two items in the array.
        i += 2;
      }
    }

    // The logic for handling streaming messages remains the same and is still needed.
    // It correctly overlays the streaming data onto the most recent turn.
    const streamingValues = Object.values(streamingMessages);
    if (streamingValues.length > 0) {
      const lastTurn = turns[turns.length - 1];
      if (lastTurn) {
        const streamA = streamingValues.find(m => m.participant === 'a');
        const streamB = streamingValues.find(m => m.participant === 'b');

        if (streamA) {
          lastTurn.modelAMessage = { ...streamA, isStreaming: true };
        }
        if (streamB) {
          lastTurn.modelBMessage = { ...streamB, isStreaming: true };
        }
      }
    }

    return turns;
  }, [messages, streamingMessages]);

  const lastTurn = conversationTurns.length > 0 ? conversationTurns[conversationTurns.length - 1] : null;

  const showFeedbackControls =
    lastTurn &&
    lastTurn.modelAMessage &&
    lastTurn.modelBMessage &&
    !lastTurn.modelAMessage.isStreaming &&
    !lastTurn.modelBMessage.isStreaming &&
    !lastTurn.userMessage.feedback;

  let messageDataForModal = expandedMessage;
  let modelNameForModal = '';

  if (expandedMessage) {
    // Check if the expanded message is currently streaming
    const streamingData = Object.values(streamingMessages).find(
      (msg) => msg.id === expandedMessage.id
    );

    if (streamingData) {
      // If so, merge its data to show the latest content
      messageDataForModal = { ...expandedMessage, ...streamingData, isStreaming: true };
    }

    // Determine the model name for the modal header
    if (expandedMessage.participant === 'a') {
      modelNameForModal = session.model_a?.display_name;
    } else if (expandedMessage.participant === 'b') {
      modelNameForModal = session.model_b?.display_name;
    }
  }

  return (
    <>
      <ExpandedMessageView
        message={messageDataForModal}
        modelName={modelNameForModal}
        onClose={handleCloseExpand}
      />

      <div ref={mainScrollRef} onScroll={handleMainScroll} className="flex-1 overflow-y-auto p-2 sm:p-4 scroll-gutter-stable">
        <div className="max-w-7xl mx-auto space-y-3 sm:space-y-5 pb-6">
          {conversationTurns.map((turn) => {
            const turnFeedback = turn.userMessage.feedback;
            return (
              <ConversationTurn
                key={turn.userMessage?.id}
                turn={turn}
                modelAName={session.mode === "compare" ? session.model_a?.display_name : "random"}
                modelBName={session.mode === "compare" ? session.model_b?.display_name : "random"}
                feedbackSelection={turnFeedback}
                hoverPreview={hoverPreview}
                onHoverPreview={setHoverPreview}
                onExpand={handleExpand}
              />
            );
          })}
          <div ref={endOfMessagesRef} />
        </div>
      </div>

      {showFeedbackControls && (
        <FeedbackSelector
          onSelect={(preference) => handlePreference(lastTurn.userMessage.id, preference)}
          onHover={setHoverPreview}
        />
      )}
    </>
  );
}