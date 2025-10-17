import { useState, useRef, useEffect } from 'react';
import { Send, LoaderCircle, Info, Image, Mic, Languages } from 'lucide-react';
import { useStreamingMessage } from '../hooks/useStreamingMessage';
import { useStreamingMessageCompare } from '../hooks/useStreamingMessagesCompare';
import { toast } from 'react-hot-toast';
import { useGuestLimitations } from '../hooks/useGuestLimitations';
import { AuthModal } from '../../auth/components/AuthModal';
import { useSelector, useDispatch } from 'react-redux';
import { createSession } from '../store/chatSlice';
import { useNavigate } from 'react-router-dom';
import { IndicTransliterate } from "@ai4bharat/indic-transliterate-transcribe";
import { API_BASE_URL } from '../../../shared/api/client';
import { TranslateIcon } from './icons/TranslateIcon';
import { LanguageSelector } from './LanguageSelector';

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
  const [isTranslateEnabled, setIsTranslateEnabled] = useState(false);
  const [selectedLang, setSelectedLang] = useState('en');
  const micButtonRef = useRef(null);
  const [voiceState, setVoiceState] = useState('idle');

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
          <div className="flex flex-col bg-white border-2 border-orange-500 rounded-xl shadow-sm">
            <IndicTransliterate
              key={`indic-${selectedLang || 'default'}-${isTranslateEnabled}`}
              customApiURL={`${API_BASE_URL}/xlit-api/generic/transliteration/`}
              enableASR={isTranslateEnabled ? true : false}
              asrApiUrl={`${API_BASE_URL}/asr-api/generic/transcribe`}
              // apiKey={`JWT ${localStorage.getItem("anudesh_access_token")}`}
              micButtonRef={micButtonRef}
              onVoiceTypingStateChange={setVoiceState}
              renderComponent={(props) => (
                <textarea
                  ref={textareaRef}
                  onInput={(e) => {
                    const textarea = e.target;
                    textarea.style.height = 'auto';
                    const scrollHeight = textarea.scrollHeight;
                    const maxHeight = isTranslateEnabled ? 120 : 96;
                    if (scrollHeight <= maxHeight) {
                      textarea.style.height = `${scrollHeight}px`;
                      textarea.style.overflowY = 'hidden';
                    } else {
                      textarea.style.height = `${maxHeight}px`;
                      textarea.style.overflowY = 'auto';
                    }
                    if (props.onInput) props.onInput(e);
                  }}
                  placeholder={isCentered ? 'Ask anything...' : 'Ask followup...'}
                  className={`w-full px-3 sm:px-4 pt-3 sm:pt-4 bg-transparent border-none focus:ring-0 focus:outline-none resize-none text-gray-800 placeholder:text-gray-500 transition-colors duration-300 text-sm sm:text-base
                   ${isCentered ? 'max-h-96' : 'max-h-32'}
                   [&::-webkit-scrollbar]:w-1.5
                   [&::-webkit-scrollbar-track]:bg-transparent
                   [&::-webkit-scrollbar-thumb]:rounded-full
                   [&::-webkit-scrollbar-thumb]:bg-gray-300
                   hover:[&::-webkit-scrollbar-thumb]:bg-gray-400`}
                  rows="1"
                  {...props}
                />
              )}
              value={input}
              onChangeText={(text) => {
                setInput(text);
              }}
              onKeyDown={handleKeyDown}
              lang={selectedLang}
              style={{
                flex: 1,
                width: "100%",
                outline: 'none',
                maxHeight: isTranslateEnabled ? '120px' : '96px',
                minHeight: isTranslateEnabled ? '30px' : '24px',
                display: 'flex',
                lineHeight: '1.5',
                resize: 'none',
                // padding: theme.spacing(0, 1),
                fontSize: '1rem',
                fontFamily: 'inherit',
                color: 'inherit',
                background: 'transparent',
                border: 'none',
              }}
              horizontalView={true}
              enabled={selectedLang !== null ? selectedLang === "en" ? false : isTranslateEnabled === false ? false : true : true}
            />
            <div className="flex items-center justify-between p-2">
              <div className="flex items-center">
                <button
                  type="button"
                  onClick={() => setIsTranslateEnabled(!isTranslateEnabled)}
                  className={`p-1.5 sm:p-2 rounded-md transition-colors disabled:opacity-50 ${isTranslateEnabled ? 'text-orange-500 hover:bg-orange-50' : 'text-gray-500 hover:bg-gray-100'}`}
                  disabled={isLoading}
                  aria-label="Toggle translation"
                >
                  {isTranslateEnabled ? <TranslateIcon className="h-5 w-5 sm:h-6 sm:w-6" fill='#f97316'/> : <TranslateIcon className="h-5 w-5 sm:h-6 sm:w-6"/>}
                </button>

                {isTranslateEnabled && (
                  <div className="flex items-center">
                    <div className="h-5 w-px bg-gray-300 mx-2" />
                    <LanguageSelector
                      value={selectedLang}
                      onChange={(e) => setSelectedLang(e.target.value)}
                    />
                  </div>
                )}
              </div>

              <div className="flex items-center gap-1">
                {isTranslateEnabled &&
                <button
                  type="button"
                  ref={micButtonRef}
                  className={`p-1.5 sm:p-2 text-gray-500 rounded-md hover:bg-gray-100 hover:text-orange-600 transition-colors disabled:opacity-50`}
                  disabled={isLoading}
                  aria-label="Voice input"
                >
                  {voiceState === 'loading' ? (
                    <LoaderCircle size={18} className="text-orange-500 animate-spin sm:w-5 sm:h-5" />
                  ) : voiceState === 'recording' ? (
                    <div className="flex items-center justify-center gap-0.5 w-5 h-5">
                      <span className="inline-block w-0.5 h-3 bg-orange-500 rounded-full animate-sound-wave"></span>
                      <span className="inline-block w-0.5 h-4 bg-orange-500 rounded-full animate-sound-wave [animation-delay:100ms]"></span>
                      <span className="inline-block w-0.5 h-2 bg-orange-500 rounded-full animate-sound-wave [animation-delay:200ms]"></span>
                      <span className="inline-block w-0.5 h-3.5 bg-orange-500 rounded-full animate-sound-wave [animation-delay:300ms]"></span>
                      <span className="inline-block w-0.5 h-2.5 bg-orange-500 rounded-full animate-sound-wave [animation-delay:400ms]"></span>
                    </div>
                  ) : (
                    <Mic size={18} className="sm:w-5 sm:h-5" />
                  )}
                </button>}
                <button
                  type="button"
                  onClick={() => toast('Image upload coming soon!')}
                  className="p-1.5 sm:p-2 text-gray-500 rounded-md hover:bg-gray-100 hover:text-orange-600 transition-colors disabled:opacity-50"
                  disabled={isLoading}
                  aria-label="Attach file"
                >
                  <Image size={18} className="sm:w-5 sm:h-5" />
                </button>
                <button
                  type="submit"
                  aria-label="Send message"
                  className={`w-8 h-8 sm:w-9 sm:h-9 flex items-center justify-center rounded-lg transition-colors
                    ${(!input.trim() || isLoading)
                      ? 'bg-transparent text-gray-500 hover:bg-gray-200 disabled:hover:bg-transparent'
                      : 'text-orange-500 hover:bg-gray-100'
                    }`
                  }
                  disabled={!input.trim() || isLoading}
                >
                  {isLoading ? (
                    <LoaderCircle size={18} className="animate-spin sm:w-5 sm:h-5" />
                  ) : (
                    <Send size={18} className="sm:w-5 sm:h-5" />
                  )}
                </button>
              </div>
            </div>
          </div>
        </form>
      </div>



      <AuthModal isOpen={showAuthPrompt} onClose={() => setShowAuthPrompt(false)} />
    </>
  );
}