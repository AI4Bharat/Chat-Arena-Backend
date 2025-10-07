import { useEffect, useState } from 'react';
import { useDispatch, useSelector } from 'react-redux';
import { fetchSessions, createSession, setActiveSession } from '../store/chatSlice';
import { logout } from '../../auth/store/authSlice';
import { Plus, MessageSquare, LogOut, User, ChevronLeft, LogIn, Clock } from 'lucide-react';
import { format, formatDistanceToNow } from 'date-fns';
import { AuthModal } from '../../auth/components/AuthModal';
import { useGuestLimitations } from '../hooks/useGuestLimitations';

export function ChatSidebar({ isOpen, onToggle }) {
  const dispatch = useDispatch();
  const { sessions, activeSession } = useSelector((state) => state.chat);
  const { user, isAnonymous } = useSelector((state) => state.auth);
  const [showAuthModal, setShowAuthModal] = useState(false);
  const {
    checkSessionLimit,
    incrementSessionCount,
    sessionCount,
    sessionLimit
  } = useGuestLimitations();

  useEffect(() => {
    dispatch(fetchSessions());
  }, [dispatch]);

  const handleNewChat = async () => {
    if (!checkSessionLimit()) {
      setShowAuthModal(true);
      return;
    }
    const result = await dispatch(createSession({ mode: 'direct' }));
    if (result.meta.requestStatus === 'fulfilled') {
      await incrementSessionCount();
    }
  };

  const handleSelectSession = (session) => {
    dispatch(setActiveSession(session));
  };

  const handleLogout = () => {
    dispatch(logout());
    window.location.reload();
  };

  const getExpiryInfo = () => {
    if (!isAnonymous || !user?.anonymous_expires_at) return null;
    const expiryDate = new Date(user.anonymous_expires_at);
    const daysLeft = Math.ceil((expiryDate - new Date()) / (1000 * 60 * 60 * 24));
    return {
      expiryDate,
      daysLeft,
      displayText: `${daysLeft} days left`
    };
  };

  const expiryInfo = getExpiryInfo();

  return (
    <>
      <div className="relative flex h-full">
        {/* Sidebar Container */}
        <div className={`${isOpen ? 'w-64' : 'w-0'} transition-all duration-300 bg-gray-900 text-white flex flex-col h-full overflow-hidden`}>
          {/* Header (will not shrink) */}
          {/* <div className="p-4 border-b border-gray-700 flex-shrink-0">
            <button
              onClick={handleNewChat}
              className="w-full flex items-center justify-center gap-2 bg-orange-600 hover:bg-orange-700 px-4 py-2 rounded-lg transition-colors"
            >
              <Plus size={20} />
              New Chat
            </button>
            {/* {isAnonymous && (
              <div className="mt-2 text-xs text-gray-400 text-center">
                <p>Sessions: {sessionCount}/{sessionLimit}</p>
              </div>
            )}
          </div> */}

          {/* Sessions List (This is the key part: it will grow and scroll) */}
          <div className="flex-1 overflow-y-auto min-h-0">
            <div className="p-2">
              {sessions.length === 0 && (
                <p className="text-gray-400 text-sm text-center mt-4">
                  No conversations yet
                </p>
              )}
              {sessions.map((session) => (
                <button
                  key={session.id}
                  onClick={() => handleSelectSession(session)}
                  className={`w-full text-left p-3 rounded-lg mb-1 hover:bg-gray-800 transition-colors ${activeSession?.id === session.id ? 'bg-gray-800' : ''
                    }`}
                >
                  <div className="flex items-center gap-2">
                    <MessageSquare size={16} />
                    <div className="flex-1 overflow-hidden">
                      <div className="text-sm font-medium truncate">
                        {session.title || `Chat ${format(new Date(session.created_at), 'MMM d')}`}
                      </div>
                      <div className="text-xs text-gray-400">
                        {session.mode} • {formatDistanceToNow(new Date(session.created_at), { addSuffix: true })}
                      </div>
                    </div>
                  </div>
                </button>
              ))}
            </div>
          </div>

          {/* User Section (will not shrink, stays at the bottom) */}
          <div className="border-t border-gray-700 p-4 flex-shrink-0">
            <div className="mb-3">
              <div className="flex items-center gap-2 mb-2">
                <div className={`w-8 h-8 rounded-full flex items-center justify-center ${isAnonymous ? 'bg-gray-600' : 'bg-orange-600'
                  }`}>
                  <User size={16} />
                </div>
                <div className="flex-1">
                  <p className="text-sm font-medium">
                    {isAnonymous ? 'Guest User' : (user?.email || user?.username)}
                  </p>
                  {isAnonymous && expiryInfo && (
                    <p className="text-xs text-gray-400 flex items-center gap-1">
                      <Clock size={12} />
                      {expiryInfo.displayText}
                    </p>
                  )}
                </div>
              </div>
            </div>

            {isAnonymous ? (
              <button
                onClick={() => setShowAuthModal(true)}
                className="w-full flex items-center justify-center gap-2 bg-orange-600 hover:bg-orange-700 px-4 py-2 rounded-lg transition-colors"
              >
                <LogIn size={16} />
                Sign in
              </button>
            ) : (
              <button
                onClick={handleLogout}
                className="w-full flex items-center justify-center gap-2 bg-gray-800 hover:bg-gray-700 px-4 py-2 rounded-lg transition-colors"
              >
                <LogOut size={16} />
                Logout
              </button>
            )}
          </div>
        </div>

        {/* Toggle Button */}
        <div className={`absolute top-4 z-10 transition-all duration-300 ${isOpen ? 'left-64' : 'left-0'}`}>
            <button
              onClick={onToggle}
              className="bg-gray-800 text-white p-1 rounded-full -translate-x-1/2 hover:bg-gray-700"
            >
              <ChevronLeft className={`transition-transform ${!isOpen ? 'rotate-180' : ''}`} size={16} />
            </button>
        </div>
      </div>

      <AuthModal isOpen={showAuthModal} onClose={() => setShowAuthModal(false)} />
    </>
  );
}