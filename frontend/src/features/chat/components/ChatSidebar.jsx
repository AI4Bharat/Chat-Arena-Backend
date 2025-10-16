import { useEffect, useState, useMemo } from 'react';
import { useDispatch, useSelector } from 'react-redux';
import { fetchSessions, setActiveSession, clearMessages } from '../store/chatSlice';
import { logout } from '../../auth/store/authSlice';
import {
  Plus,
  MessageSquare,
  LogOut,
  User,
  LogIn,
  Clock,
  Bot,
  PanelLeftOpen,
  PanelLeftClose
} from 'lucide-react';
import { AuthModal } from '../../auth/components/AuthModal';
import { useNavigate, useParams } from 'react-router-dom';
import { groupSessionsByDate } from '../utils/dateUtils';
import { SidebarItem } from './SidebarItem';

const SessionItem = ({ session, isActive, onClick }) => (
  <button
    onClick={onClick}
    className={`w-full text-left p-2 sm:p-2.5 rounded-lg mb-1 transition-colors flex items-center gap-2 sm:gap-3 text-xs sm:text-sm font-medium truncate ${isActive
      ? 'bg-orange-100 text-orange-800'
      : 'text-gray-700 hover:bg-gray-100'
      }`}
  >
    <MessageSquare className="flex-shrink-0" size={14} />
    <span className="flex-1 truncate">
      {session.title || 'New Conversation'}
    </span>
  </button>
);


export function ChatSidebar({ isOpen, onToggle }) {
  const dispatch = useDispatch();
  const navigate = useNavigate();
  const { sessionId } = useParams();
  const { sessions } = useSelector((state) => state.chat);
  const { user, isAnonymous } = useSelector((state) => state.auth);
  const [showAuthModal, setShowAuthModal] = useState(false);

  const groupedSessions = useMemo(() => groupSessionsByDate(sessions), [sessions]);

  useEffect(() => {
    dispatch(fetchSessions());
  }, [dispatch]);

  const handleNewChat = () => {
    dispatch(setActiveSession(null));
    dispatch(clearMessages());
    navigate('/chat');
    // Auto-close sidebar on small screens after starting a new chat
    if (typeof window !== 'undefined' && window.innerWidth < 768 && onToggle) {
      onToggle();
    }
  };

  const handleSelectSession = (session) => {
    navigate(`/chat/${session.id}`);
    // Auto-close sidebar on small screens after selecting a session
    if (typeof window !== 'undefined' && window.innerWidth < 768 && onToggle) {
      onToggle();
    }
  };

  const handleLogout = () => {
    dispatch(logout());
    window.location.reload();
  };

  const getExpiryInfo = () => {
    if (!isAnonymous || !user?.anonymous_expires_at) return null;
    const expiryDate = new Date(user.anonymous_expires_at);
    const daysLeft = Math.ceil((expiryDate - new Date()) / (1000 * 60 * 60 * 24));
    return { displayText: `${daysLeft} day${daysLeft !== 1 ? 's' : ''} left` };
  };

  const expiryInfo = getExpiryInfo();

  return (
    <>
      <div
        className={
          `bg-white border-r border-gray-200 flex flex-col h-full transition-all duration-300
          fixed inset-y-0 left-0 z-40 w-64 transform ${isOpen ? 'translate-x-0' : '-translate-x-full'}
          md:relative md:z-auto md:transform-none ${isOpen ? 'md:w-64' : 'md:w-14'}`
        }
      >

        <div className="flex-shrink-0">
          <div className="flex items-center h-[65px] px-3 sm:px-4 border-b border-gray-200">
            {isOpen ? (
              <div className="flex items-center justify-between w-full">
                <div className="flex items-center gap-2 overflow-hidden min-w-0">
                  <Bot className="text-orange-500 flex-shrink-0" size={20} />
                  <span className="font-bold text-base sm:text-lg whitespace-nowrap truncate">AI Arena</span>
                </div>
                <button onClick={onToggle} className="p-1.5 rounded-lg hover:bg-gray-100 flex-shrink-0">
                  <PanelLeftClose size={18} />
                </button>
              </div>
            ) : (
              <div className="flex items-center justify-center w-full">
                <button onClick={onToggle} className="relative group p-1.5 rounded-lg hover:bg-gray-100">
                  <Bot size={20} className="text-orange-500 transition-transform duration-300 group-hover:scale-0" />
                  <PanelLeftOpen size={18} className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 text-gray-700 transition-transform duration-300 scale-0 group-hover:scale-100" />
                </button>
              </div>
            )}
          </div>

          <div className="p-2">
            <SidebarItem icon={Plus} text="New Chat" isOpen={isOpen} onClick={handleNewChat} bordered={isOpen} />
          </div>
        </div>

        <div className={`flex-1 overflow-y-auto min-h-0 transition-opacity duration-200 ${isOpen ? 'opacity-100 p-2' : 'opacity-0'} ${isOpen ? '' : 'pointer-events-none md:pointer-events-auto'}`}>
          {isOpen && (
            groupedSessions.length === 0 ? (
              <p className="text-gray-500 text-sm text-center mt-4 px-2">
                Your chat history will appear here.
              </p>
            ) : (
              groupedSessions.map((group) => (
                <div key={group.title} className="mb-4">
                  <h3 className="text-xs font-semibold text-gray-400 uppercase px-2.5 mb-2">
                    {group.title}
                  </h3>
                  {group.sessions.map((session) => (
                    <SessionItem
                      key={session.id}
                      session={session}
                      isActive={sessionId === session.id}
                      onClick={() => handleSelectSession(session)}
                    />
                  ))}
                </div>
              ))
            )
          )}
        </div>

        <div className="border-t border-gray-200 p-2 flex-shrink-0">
          {isAnonymous ? (
            <SidebarItem icon={LogIn} text="Sign in to save" isOpen={isOpen} onClick={() => setShowAuthModal(true)} />
          ) : (
            <SidebarItem icon={LogOut} text="Logout" isOpen={isOpen} onClick={handleLogout} />
          )}

          <div className={`flex items-center justify-center p-1.5 sm:p-2 mt-1 rounded-lg cursor-pointer ${isOpen ? "gap-2 sm:gap-3" : ""}`}>
            <div className={`w-8 h-8 sm:w-9 sm:h-9 rounded-full flex items-center justify-center flex-shrink-0 ${isAnonymous ? 'bg-gray-200' : 'bg-orange-500 text-white'}`}>
              <User size={16} className="sm:w-[18px] sm:h-[18px]" />
            </div>
            <div className={`overflow-hidden transition-all duration-300 ease-in-out ${isOpen ? "max-w-[120px] sm:max-w-[150px]" : "max-w-0"}`}>
              <p className="text-xs sm:text-sm font-semibold whitespace-nowrap truncate">
                {isAnonymous ? 'Guest User' : (user?.email || user?.username)}
              </p>
            </div>
          </div>
        </div>
      </div>
      <AuthModal isOpen={showAuthModal} onClose={() => setShowAuthModal(false)} />
    </>
  );
}