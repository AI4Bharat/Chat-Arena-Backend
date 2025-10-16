import { useState, useEffect } from 'react';
import { useSelector, useDispatch } from 'react-redux';
import { ChatSidebar } from './ChatSidebar';
import { ChatWindow } from './ChatWindow';
import { ModelSelector } from './ModelSelector';
import { SessionActions } from './SessionActions';
import { useNavigate, useParams } from 'react-router-dom';
import { AuthPromptBanner } from '../../auth/components/AuthPromptBanner';
import { fetchSessionById, setActiveSession, clearMessages } from '../store/chatSlice';
import { PanelLeftOpen, Plus } from 'lucide-react';

export function ChatLayout() {
  const { sessionId } = useParams();
  const navigate = useNavigate();
  const dispatch = useDispatch();
  const { activeSession } = useSelector((state) => state.chat);
  const [isSidebarOpen, setIsSidebarOpen] = useState(true);

  // Initialize sidebar state based on screen size and keep in sync on resize
  useEffect(() => {
    const applyResponsiveSidebar = () => {
      if (typeof window === 'undefined') return;
      const isDesktop = window.innerWidth >= 768; // md breakpoint
      setIsSidebarOpen(isDesktop);
    };
    applyResponsiveSidebar();
    window.addEventListener('resize', applyResponsiveSidebar);
    return () => window.removeEventListener('resize', applyResponsiveSidebar);
  }, []);

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

  const handleNewChat = () => {
    dispatch(setActiveSession(null));
    dispatch(clearMessages());
    navigate('/chat');
  };

  return (
    <div className="flex flex-col h-screen bg-gray-50">
      {/* Auth Prompt Banner */}
      <AuthPromptBanner />

      <div className="flex flex-1 overflow-hidden">
        {/* Sidebar */}
        <ChatSidebar isOpen={isSidebarOpen} onToggle={() => setIsSidebarOpen(!isSidebarOpen)} />

        {/* Main Chat Area */}
        <div className="flex-1 flex flex-col overflow-hidden">
          <header className="bg-white border-b border-gray-200 px-2 sm:px-4 md:px-6 flex-shrink-0 md:h-[65px]">
            {/* Mobile (sm and below): two-row layout */}
            <div className="md:hidden">
              {/* Row 1: toggle, centered mode selector, new chat on right when sidebar hidden */}
              <div className="flex items-center justify-between w-full min-w-0 h-[48px]">
                <div className="flex items-center gap-2 sm:gap-3 min-w-0">
                  {/* Mobile sidebar toggle */}
                  <button
                    className="p-1.5 sm:p-2 rounded-lg hover:bg-gray-100 flex-shrink-0"
                    aria-label="Open sidebar"
                    onClick={() => setIsSidebarOpen(true)}
                  >
                    <PanelLeftOpen size={20} className="sm:w-6 sm:h-6" />
                  </button>
                </div>
                <div className="flex-1 min-w-0 flex items-center justify-center">
                  <ModelSelector variant="mode" />
                </div>
                <div className="flex items-center gap-2 sm:gap-3">
                  {!isSidebarOpen && (
                    <button
                      onClick={handleNewChat}
                      className="p-2 rounded-lg hover:bg-gray-100"
                      aria-label="New chat"
                    >
                      <Plus size={20} />
                    </button>
                  )}
                </div>
              </div>
              {/* Row 2: centered model selectors for direct/compare */}
              <div className="pb-2">
                <ModelSelector variant="models" />
              </div>
            </div>

            {/* Desktop (md+): single-row layout like earlier */}
            <div className="hidden md:flex items-center h-[65px]">
              <div className="flex items-center gap-3 w-full min-w-0">
                <div className="min-w-0 flex-1">
                  <ModelSelector />
                </div>
              </div>
            </div>
          </header>

          {/* Chat Window */}
          <ChatWindow />
        </div>

        {/* Mobile backdrop overlay when sidebar is open */}
        {isSidebarOpen && (
          <div
            className="fixed inset-0 bg-black/30 z-30 md:hidden"
            onClick={() => setIsSidebarOpen(false)}
          />
        )}
      </div>
    </div>
  );
}