import { createSlice, createAsyncThunk } from '@reduxjs/toolkit';
import { apiClient } from '../../../shared/api/client';
import { endpoints } from '../../../shared/api/endpoints';
import { userService } from '../services/userService';

// Async thunks
export const loginWithGoogle = createAsyncThunk(
  'auth/loginWithGoogle',
  async (idToken, { getState }) => {
    // Get anonymous token if exists
    const anonymousToken = localStorage.getItem('anonymous_token');
    
    // Set anonymous token in header if exists for merging
    if (anonymousToken) {
      apiClient.defaults.headers['X-Anonymous-Token'] = anonymousToken;
    }
    
    const response = await apiClient.post(endpoints.auth.google, { 
      id_token: idToken
    });
    
    // Store JWT tokens
    userService.storeTokens(response.data.tokens);
    
    // Clean up anonymous token after successful merge
    if (anonymousToken) {
      localStorage.removeItem('anonymous_token');
      delete apiClient.defaults.headers['X-Anonymous-Token'];
    }
    
    return response.data;
  }
);

export const loginAnonymously = createAsyncThunk(
  'auth/loginAnonymously',
  async (displayName) => {
    const response = await apiClient.post(endpoints.auth.anonymous, {
      display_name: displayName
    });
    
    // Store JWT tokens and anonymous token
    userService.storeTokens(response.data.tokens);
    if (response.data.anonymous_token) {
      localStorage.setItem('anonymous_token', response.data.anonymous_token);
    }
    
    return response.data;
  }
);

export const fetchCurrentUser = createAsyncThunk(
  'auth/fetchCurrentUser',
  async (_, { rejectWithValue }) => {
    try {
      const response = await apiClient.get(endpoints.auth.currentUser);
      return response.data;
    } catch (error) {
      if (error.response?.status === 401) {
        return rejectWithValue('Authentication failed');
      }
      return rejectWithValue(error.message);
    }
  }
);

export const updatePreferences = createAsyncThunk(
  'auth/updatePreferences',
  async (preferences) => {
    const response = await apiClient.patch(endpoints.auth.updatePreferences, preferences);
    return response.data;
  }
);

export const refreshToken = createAsyncThunk(
  'auth/refreshToken',
  async () => {
    const response = await userService.refreshAccessToken();
    return response;
  }
);

const authSlice = createSlice({
  name: 'auth',
  initialState: {
    user: null,
    isAuthenticated: false,
    isAnonymous: false,
    loading: false,
    error: null,
    initialized: false,
  },
  reducers: {
    logout: (state) => {
      state.user = null;
      state.isAuthenticated = false;
      state.isAnonymous = false;
      state.error = null;
      state.initialized = false;
      // Clear all tokens
      userService.clearTokens();
    },
    setLoading: (state, action) => {
      state.loading = action.payload;
    },
    clearError: (state) => {
      state.error = null;
    },
    setInitialized: (state) => {
      state.initialized = true;
    },
  },
  extraReducers: (builder) => {
    // Google login
    builder
      .addCase(loginWithGoogle.pending, (state) => {
        state.loading = true;
        state.error = null;
      })
      .addCase(loginWithGoogle.fulfilled, (state, action) => {
        state.loading = false;
        state.user = action.payload.user;
        state.isAuthenticated = true;
        state.isAnonymous = false;
        state.error = null;
      })
      .addCase(loginWithGoogle.rejected, (state, action) => {
        state.loading = false;
        state.error = action.error.message;
      });
    
    // Anonymous login
    builder
      .addCase(loginAnonymously.pending, (state) => {
        state.loading = true;
        state.error = null;
      })
      .addCase(loginAnonymously.fulfilled, (state, action) => {
        state.loading = false;
        state.user = action.payload.user;
        state.isAuthenticated = true;
        state.isAnonymous = true;
        state.error = null;
        state.initialized = true;
      })
      .addCase(loginAnonymously.rejected, (state, action) => {
        state.loading = false;
        state.error = action.error.message;
        state.initialized = true;
      });
    
    // Fetch current user
    builder
      .addCase(fetchCurrentUser.pending, (state) => {
        state.loading = true;
      })
      .addCase(fetchCurrentUser.fulfilled, (state, action) => {
        state.loading = false;
        state.user = action.payload;
        state.isAuthenticated = true;
        state.isAnonymous = action.payload.is_anonymous;
        state.error = null;
        state.initialized = true;
      })
      .addCase(fetchCurrentUser.rejected, (state, action) => {
        state.loading = false;
        state.isAuthenticated = false;
        state.error = action.payload;
        state.initialized = true;
      });
    
    // Update preferences
    builder
      .addCase(updatePreferences.fulfilled, (state, action) => {
        state.user = action.payload;
      });
    
    // Refresh token
    builder
      .addCase(refreshToken.fulfilled, (state) => {
        // Token refreshed successfully, no state change needed
      })
      .addCase(refreshToken.rejected, (state) => {
        // Refresh failed, logout user
        state.user = null;
        state.isAuthenticated = false;
        state.isAnonymous = false;
        userService.clearTokens();
      });
  },
});

export const { logout, setLoading, clearError, setInitialized } = authSlice.actions;
export default authSlice.reducer;