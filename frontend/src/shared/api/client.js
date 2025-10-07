import axios from 'axios';
import { userService } from '../../features/auth/services/userService';
import { store } from '../../app/store';
import { logout } from '../../features/auth/store/authSlice';

const API_BASE_URL = process.env.REACT_APP_API_URL || 'http://localhost:8000/api';
const WS_BASE_URL = process.env.REACT_APP_WS_URL || 'ws://localhost:8000/ws';

// Create axios instance
const apiClient = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
  withCredentials: true,
});

// Track if we're currently refreshing the token
let isRefreshing = false;
let refreshSubscribers = [];
let failedRequestsCount = 0;
const MAX_RETRY_ATTEMPTS = 3;

// Reset failed count periodically
setInterval(() => {
  failedRequestsCount = 0;
}, 60000); // Reset every minute

function subscribeTokenRefresh(cb) {
  refreshSubscribers.push(cb);
}

// Call all refresh subscribers
function onRefreshed(token) {
  refreshSubscribers.map((cb) => cb(token));
  refreshSubscribers = [];
}

// Request interceptor for auth
apiClient.interceptors.request.use(
  (config) => {
    // Skip auth for these endpoints
    const skipAuthEndpoints = ['/auth/', '/public/'];
    const shouldSkipAuth = skipAuthEndpoints.some(endpoint => 
      config.url?.includes(endpoint)
    );
    
    if (!shouldSkipAuth) {
      const accessToken = localStorage.getItem('access_token');
      if (accessToken) {
        config.headers.Authorization = `Bearer ${accessToken}`;
      } else {
        const anonymousToken = localStorage.getItem('anonymous_token');
        if (anonymousToken) {
          config.headers['X-Anonymous-Token'] = anonymousToken;
        }
      }
    }
    
    return config;
  },
  (error) => Promise.reject(error)
);

// Response interceptor for error handling and token refresh
apiClient.interceptors.response.use(
  (response) => {
    // Reset failed count on any successful request
    failedRequestsCount = 0;
    return response;
  },
  async (error) => {
    const originalRequest = error.config;
    
    // Prevent infinite loops
    if (failedRequestsCount >= MAX_RETRY_ATTEMPTS) {
      console.error('Max retry attempts reached, stopping requests');
      store.dispatch(logout());
      return Promise.reject(new Error('Authentication failed. Please refresh the page.'));
    }
    
    // Handle 401 errors
    if (error.response?.status === 401 && !originalRequest._retry) {
      // Skip retry for auth endpoints
      if (originalRequest.url?.includes('/auth/')) {
        return Promise.reject(error);
      }
      
      // Mark request as retried
      originalRequest._retry = true;
      failedRequestsCount++;
      
      if (!isRefreshing) {
        isRefreshing = true;
        
        try {
          const refreshToken = localStorage.getItem('refresh_token');
          
          // If no refresh token, don't try to refresh
          if (!refreshToken) {
            throw new Error('No refresh token available');
          }
          
          // Don't use apiClient here to avoid interceptor loop
          const response = await axios.post(
            `${API_BASE_URL}/auth/refresh/`,
            { refresh: refreshToken },
            { 
              headers: { 'Content-Type': 'application/json' },
              // Add timeout to prevent hanging
              timeout: 5000
            }
          );
          
          const { access } = response.data;
          localStorage.setItem('access_token', access);
          
          // Reset failed count on successful refresh
          failedRequestsCount = 0;
          isRefreshing = false;
          onRefreshed(access);
          
          // Retry original request
          originalRequest.headers.Authorization = `Bearer ${access}`;
          return apiClient(originalRequest);
          
        } catch (refreshError) {
          isRefreshing = false;
          refreshSubscribers = [];
          
          // Only clear tokens and logout, don't redirect
          userService.clearTokens();
          store.dispatch(logout());
          
          // Return a rejected promise with a clear error
          return Promise.reject(new Error('Session expired. Please sign in again.'));
        }
      } else {
        // Wait for ongoing refresh
        return new Promise((resolve, reject) => {
          subscribeTokenRefresh((token) => {
            originalRequest.headers.Authorization = `Bearer ${token}`;
            resolve(apiClient(originalRequest));
          });
          
          // Timeout for waiting
          setTimeout(() => {
            reject(new Error('Token refresh timeout'));
          }, 10000);
        });
      }
    }
    
    return Promise.reject(error);
  }
);

// Add abort controller support
export const createAbortController = () => new AbortController();

// WebSocket connection helper with better error handling
export const createWebSocketConnection = (path, options = {}) => {
  const token = localStorage.getItem('access_token');
  const anonymousToken = localStorage.getItem('anonymous_token');
  
  // Don't create connection without auth
  if (!token && !anonymousToken) {
    throw new Error('No authentication token available');
  }
  
  let wsUrl = `${WS_BASE_URL}${path}`;
  const queryParams = [];
  
  if (token) {
    queryParams.push(`token=${token}`);
  } else if (anonymousToken) {
    queryParams.push(`anonymous_token=${anonymousToken}`);
  }
  
  Object.entries(options).forEach(([key, value]) => {
    if (value !== undefined && value !== null) {
      queryParams.push(`${key}=${encodeURIComponent(value)}`);
    }
  });
  
  if (queryParams.length > 0) {
    wsUrl += `?${queryParams.join('&')}`;
  }
  
  return new WebSocket(wsUrl);
};

export { apiClient, API_BASE_URL, WS_BASE_URL };