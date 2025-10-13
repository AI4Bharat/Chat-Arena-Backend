import { createSlice, createAsyncThunk } from '@reduxjs/toolkit';
import { apiClient } from '../../../shared/api/client';
import { endpoints } from '../../../shared/api/endpoints';

export const createSession = createAsyncThunk(
  'chat/createSession',
  async ({ mode, modelA, modelB }) => {
    const response = await apiClient.post(endpoints.sessions.create, {
      mode,
      model_a_id: modelA,
      model_b_id: modelB,
    });
    return response.data;
  }
);

export const fetchSessions = createAsyncThunk(
  'chat/fetchSessions',
  async () => {
    const response = await apiClient.get(endpoints.sessions.list);
    return response.data;
  }
);

const chatSlice = createSlice({
  name: 'chat',
  initialState: {
    sessions: [],
    activeSession: null,
    messages: {},
    streamingMessages: {},
    loading: false,
    error: null,
  },
  reducers: {
    setActiveSession: (state, action) => {
      state.activeSession = action.payload;
    },
    addMessage: (state, action) => {
      const { sessionId, message } = action.payload;
      if (!state.messages[sessionId]) {
        state.messages[sessionId] = [];
      }
      state.messages[sessionId].push(message);
    },
    updateStreamingMessage: (state, action) => {
      const { sessionId, messageId, chunk, isComplete, participant = 'a' } = action.payload;

      if (!state.streamingMessages[sessionId]) {
        state.streamingMessages[sessionId] = {};
      }

      if (!state.streamingMessages[sessionId][messageId]) {
        state.streamingMessages[sessionId][messageId] = {
          content: '',
          isComplete: false,
        };
      }

      state.streamingMessages[sessionId][messageId].content += chunk;
      state.streamingMessages[sessionId][messageId].participant = participant;
      state.streamingMessages[sessionId][messageId].isComplete = isComplete;

      if (isComplete) {
        // Move to regular messages
        const message = {
          id: messageId,
          content: state.streamingMessages[sessionId][messageId].content,
          role: 'assistant',
          timestamp: new Date().toISOString(),
          participant: participant,
        };

        if (!state.messages[sessionId]) {
          state.messages[sessionId] = [];
        }
        state.messages[sessionId].push(message);

        delete state.streamingMessages[sessionId][messageId];
      }
    },
    setSessionState: (state, action) => {
      const { sessionId, messages, sessionData } = action.payload;
      state.messages[sessionId] = messages || [];
      const sessionIndex = state.sessions.findIndex(s => s.id === sessionId);
      if (sessionIndex !== -1 && sessionData) {
        state.sessions[sessionIndex] = { ...state.sessions[sessionIndex], ...sessionData };
      }
    },
    updateMessageFeedback: (state, action) => {
      const { sessionId, messageId, feedback } = action.payload;
      const messageIndex = state.messages[sessionId].findIndex(msg => msg.id === messageId);
      if (messageIndex !== -1) {
        state.messages[sessionId][messageIndex].feedback = feedback;
      }
    }
  },
  extraReducers: (builder) => {
    builder
      .addCase(createSession.fulfilled, (state, action) => {
        state.sessions.unshift(action.payload);
        state.activeSession = action.payload;
      })
      .addCase(fetchSessions.fulfilled, (state, action) => {
        state.sessions = action.payload;
      });
  },
});

export const { setActiveSession, addMessage, updateStreamingMessage, setSessionState, updateMessageFeedback } = chatSlice.actions;
export default chatSlice.reducer;