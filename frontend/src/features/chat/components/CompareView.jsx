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
    for (let i = 0; i < messages.length; i++) {
      if (messages[i].role === 'user') {
        const userMessage = messages[i];
        const potentialResponse1 = messages[i + 1];
        const potentialResponse2 = messages[i + 2];
        let modelAMessage = null;
        let modelBMessage = null;

        if (potentialResponse1 && potentialResponse1.role === 'assistant') {
          if (potentialResponse1.participant === 'a') modelAMessage = potentialResponse1;
          else modelBMessage = potentialResponse1;
        }
        if (potentialResponse2 && potentialResponse2.role === 'assistant') {
          if (potentialResponse2.participant === 'a') modelAMessage = potentialResponse2;
          else modelBMessage = potentialResponse2;
        }
        turns.push({ userMessage, modelAMessage, modelBMessage });
        i += 2;
      }
    }

    const streamingValues = Object.values(streamingMessages);
    if (streamingValues.length > 0) {
      const lastTurn = turns[turns.length - 1];
      if (lastTurn) {
        const streamA = streamingValues.find(m => m.participant === 'a');
        const streamB = streamingValues.find(m => m.participant === 'b');
        if (streamA) lastTurn.modelAMessage = { ...streamA, isStreaming: true };
        if (streamB) lastTurn.modelBMessage = { ...streamB, isStreaming: true };
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
    const parentTurn = conversationTurns.find(
      (turn) =>
        turn.modelAMessage?.id === expandedMessage.id ||
        turn.modelBMessage?.id === expandedMessage.id
    );
    const hasFeedbackForThisTurn = !!parentTurn?.userMessage.feedback;

    const streamingData = Object.values(streamingMessages).find(
      (msg) => msg.id === expandedMessage.id
    );
    if (streamingData) {
      messageDataForModal = { ...expandedMessage, ...streamingData, isStreaming: true };
    }

    const participant = expandedMessage.participant;
    const isModelA = participant === 'a';
    
    if (session.mode === 'compare' || (session.mode === 'random' && hasFeedbackForThisTurn)) {
      modelNameForModal = isModelA ? session.model_a?.display_name : session.model_b?.display_name;
    } else {
      modelNameForModal = isModelA ? 'Model A' : 'Model B';
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
            
            const getModelName = (participant) => {
              if (session.mode === "compare") {
                return participant === 'a' ? session.model_a?.display_name : session.model_b?.display_name;
              }
              if (turnFeedback) {
                 return participant === 'a' ? session.model_a?.display_name : session.model_b?.display_name;
              }
              return participant === 'a' ? "Model A" : "Model B";
            };

            const modelAName = getModelName('a');
            const modelBName = getModelName('b');
            
            return (
              <ConversationTurn
                key={turn.userMessage?.id}
                turn={turn}
                modelAName={modelAName}
                modelBName={modelBName}
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