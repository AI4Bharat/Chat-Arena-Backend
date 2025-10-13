import { useEffect, useRef, useState, useCallback } from 'react';
import { useDispatch, useSelector } from 'react-redux';
import { createWebSocketConnection, WS_BASE_URL } from '../../../shared/api/client';
import { updateStreamingMessage, setSessionState } from '../store/chatSlice';
import { toast } from 'react-hot-toast';
import { userService } from '../../auth/services/userService';

export function useWebSocket(sessionId) {
  const dispatch = useDispatch();
  const ws = useRef(null);
  const { user } = useSelector((state) => state.auth);
  const [isConnected, setIsConnected] = useState(false);
  const reconnectTimer = useRef(null);
  const reconnectAttempts = useRef(0);
  const maxReconnectAttempts = 5;
  const authFailures = useRef(0);
  const maxAuthFailures = 2;
  const { activeSession, messages } = useSelector((state) => state.chat);

  const connect = useCallback(async () => {
    if (!sessionId || !user) return;
    
    // Check if we've exceeded auth failures
    if (authFailures.current >= maxAuthFailures) {
      console.error('Max auth failures reached, not reconnecting');
      toast.error('Authentication failed. Please refresh the page.');
      return;
    }

    try {
      // Create WebSocket with proper error handling
      ws.current = createWebSocketConnection(`/chat/session/${sessionId}/`);

      ws.current.onopen = () => {
        console.log('WebSocket connected');
        setIsConnected(true);
        reconnectAttempts.current = 0;
        authFailures.current = 0; // Reset auth failures on successful connection
      };

      ws.current.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          
          switch (data.type) {
            case 'connection_established':
              console.log('Connection established:', data);
              break;
              
            case 'message_chunk':
              dispatch(updateStreamingMessage({
                sessionId,
                messageId: data.message_id,
                chunk: data.chunk,
                isComplete: false,
              }));
              break;
              
            case 'message_complete':
              dispatch(updateStreamingMessage({
                sessionId,
                messageId: data.message_id,
                chunk: '',
                isComplete: true,
              }));
              break;
              
            case 'session_state':
              if (!messages[sessionId]?.length) {
                dispatch(setSessionState({
                  sessionId,
                  messages: data.messages,
                  sessionData: data.session
                }));
              }
              break;
              
            case 'error':
              toast.error(data.message);
              break;
              
            default:
              console.log('Received message:', data.type, data);
          }
        } catch (error) {
          console.error('Failed to parse WebSocket message:', error);
        }
      };

      ws.current.onerror = (error) => {
        console.error('WebSocket error:', error);
      };

      ws.current.onclose = async (event) => {
        console.log('WebSocket disconnected:', event.code, event.reason);
        setIsConnected(false);

        // Clean closure, don't reconnect
        if (event.code === 1000) {
          return;
        }

        // Authentication failure codes
        if (event.code === 1006 || event.code === 1008 || event.reason?.includes('auth')) {
          authFailures.current++;
          
          if (authFailures.current >= maxAuthFailures) {
            toast.error('Authentication failed. Please sign in again.');
            return;
          }
          
          // Try to refresh token ONCE
          const refreshToken = localStorage.getItem('refresh_token');
          if (refreshToken && authFailures.current === 1) {
            try {
              await userService.refreshAccessToken();
              // Immediate reconnect with new token
              setTimeout(() => connect(), 100);
              return;
            } catch (error) {
              console.error('Token refresh failed:', error);
              toast.error('Session expired. Please sign in again.');
              return;
            }
          }
          
          return; // Don't reconnect on auth failures
        }

        // For other errors, implement exponential backoff
        if (reconnectAttempts.current < maxReconnectAttempts) {
          reconnectAttempts.current++;
          const delay = Math.min(1000 * Math.pow(2, reconnectAttempts.current - 1), 30000);
          
          console.log(`Reconnecting in ${delay}ms... (attempt ${reconnectAttempts.current})`);
          reconnectTimer.current = setTimeout(connect, delay);
        } else {
          toast.error('Connection lost. Please refresh the page.');
        }
      };
    } catch (error) {
      console.error('Failed to create WebSocket connection:', error);
      setIsConnected(false);
      
      // Don't retry if no auth token
      if (error.message.includes('No authentication token')) {
        return;
      }
    }
  }, [sessionId, user, dispatch]);

  const disconnect = useCallback(() => {
    if (reconnectTimer.current) {
      clearTimeout(reconnectTimer.current);
      reconnectTimer.current = null;
    }
    
    if (ws.current && ws.current.readyState !== WebSocket.CLOSED) {
      ws.current.close(1000, 'Client disconnect');
      ws.current = null;
    }
    
    setIsConnected(false);
  }, []);

  const sendMessage = useCallback((message) => {
    if (ws.current && ws.current.readyState === WebSocket.OPEN) {
      ws.current.send(JSON.stringify(message));
    } else {
      toast.error('Not connected. Please wait...');
      if (!isConnected && reconnectAttempts.current === 0) {
        connect();
      }
    }
  }, [connect, isConnected]);

  // Connect on mount
  useEffect(() => {
    connect();
    return () => disconnect();
  }, [sessionId]); // Only reconnect when sessionId changes

  // Reset auth failures when user changes
  useEffect(() => {
    authFailures.current = 0;
  }, [user?.id]);

  return { 
    sendMessage, 
    isConnected,
    reconnect: connect,
    disconnect 
  };
}