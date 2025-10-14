import { useState, useEffect } from 'react';
import { useSelector, useDispatch } from 'react-redux';
import { ChatSidebar } from './ChatSidebar';
import { ChatWindow } from './ChatWindow';
import { ModelSelector } from './ModelSelector';
import { SessionActions } from './SessionActions';
import { useParams } from 'react-router-dom';
import { AuthPromptBanner } from '../../auth/components/AuthPromptBanner';
import { fetchSessionById, setActiveSession } from '../store/chatSlice';

export function ChatLayout() {
  const { sessionId } = useParams();
  const dispatch = useDispatch();
  const { activeSession } = useSelector((state) => state.chat);
  const [isSidebarOpen, setIsSidebarOpen] = useState(true);

  useEffect(() => {
    if (sessionId) {
      if (!activeSession || activeSession.id !== sessionId) {
        dispatch(fetchSessionById(sessionId));
      }
    } else {
      if (activeSession) {
        dispatch(setActiveSession(null));
      }
    }
  }, [sessionId, dispatch]);

  return (
    <div className="flex flex-col h-screen">
      {/* Auth Prompt Banner */}
      <AuthPromptBanner />

      <div className="flex flex-1 overflow-hidden">
        {/* Sidebar */}
        <ChatSidebar isOpen={isSidebarOpen} onToggle={() => setIsSidebarOpen(!isSidebarOpen)} />

        {/* Main Chat Area */}
        <div className="flex-1 flex flex-col overflow-hidden">
          {/* Header */}
          <header className="bg-white shadow-sm border-b border-gray-200 px-6 py-4 flex-shrink-0">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-4">
                <h1 className="text-xl font-semibold text-gray-900">
                  {activeSession ? `Session: ${activeSession.title || activeSession.id.slice(0, 8)}` : 'New Chat'}
                </h1>
                {activeSession && <SessionActions sessionId={activeSession.id} />}
              </div>
              <ModelSelector />
            </div>
          </header>

          {/* Chat Window */}
          <ChatWindow />
        </div>
      </div>
    </div>
  );
}