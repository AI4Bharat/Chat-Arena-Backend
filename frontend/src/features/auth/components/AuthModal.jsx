import { useEffect, useState } from 'react';
import { useDispatch, useSelector } from 'react-redux';
import { loginWithGoogle, loginAnonymously } from '../store/authSlice';
import { X, Shield, Clock, User, Sparkles } from 'lucide-react';
import { toast } from 'react-hot-toast';
import { initializeApp } from 'firebase/app';
import { getAuth, signInWithPopup, GoogleAuthProvider, signInAnonymously } from 'firebase/auth';
import { fetchSessions } from '../../chat/store/chatSlice';

// Initialize Firebase (do this once in your app)
const firebaseConfig = {
  apiKey: process.env.REACT_APP_FIREBASE_API_KEY,
  authDomain: process.env.REACT_APP_FIREBASE_AUTH_DOMAIN,
  projectId: process.env.REACT_APP_FIREBASE_PROJECT_ID,
  storageBucket: process.env.REACT_APP_FIREBASE_STORAGE_BUCKET,
  messagingSenderId: process.env.REACT_APP_FIREBASE_MESSAGING_SENDER_ID,
  appId: process.env.REACT_APP_FIREBASE_APP_ID
};

const app = initializeApp(firebaseConfig);
const auth = getAuth(app);
const googleProvider = new GoogleAuthProvider();

export function AuthModal({ isOpen, onClose }) {
  const dispatch = useDispatch();
  const { loading, isAnonymous, error } = useSelector((state) => state.auth);
  const [isSigningIn, setIsSigningIn] = useState(false);

  const handleGoogleSignIn = async () => {
    setIsSigningIn(true);
    try {
      // Use Firebase's signInWithPopup
      const result = await signInWithPopup(auth, googleProvider);
      
      // Get the ID token
      const idToken = await result.user.getIdToken();
      
      // Send to backend
      await dispatch(loginWithGoogle(idToken)).unwrap();

      dispatch(fetchSessions());
      
      toast.success('Successfully signed in with Google!');
      onClose();
      
    } catch (error) {
      console.error('Google sign in error:', error);
      
      // Handle specific Firebase auth errors
      if (error.code === 'auth/popup-closed-by-user') {
        toast.error('Sign in cancelled');
      } else if (error.code === 'auth/popup-blocked') {
        toast.error('Popup blocked. Please allow popups for this site.');
      } else {
        toast.error(error.message || 'Failed to sign in with Google');
      }
    } finally {
      setIsSigningIn(false);
    }
  };

  const handleContinueAsGuest = async () => {
    try {
      await dispatch(loginAnonymously()).unwrap();
      toast.success('Continuing as guest');
      onClose();
    } catch (error) {
      console.error('Anonymous login error:', error);
      toast.error('Failed to continue as guest');
    }
  };

  if (!isOpen) return null;

  return (
    <>
      {/* Backdrop */}
      <div
        className="fixed inset-0 bg-black bg-opacity-50 backdrop-blur-sm z-40"
        onClick={onClose}
      />

      {/* Modal */}
      <div className="fixed inset-0 flex items-center justify-center z-50 p-4">
        <div className="bg-white rounded-2xl shadow-xl max-w-md w-full p-4 sm:p-6 relative max-h-[90vh] overflow-y-auto">
          {/* Close button */}
          <button
            onClick={onClose}
            className="absolute top-4 right-4 text-gray-400 hover:text-gray-600 transition-colors"
          >
            <X size={20} />
          </button>

          {/* Content */}
          <div className="text-center mb-6">
            <div className="w-16 h-16 bg-orange-100 rounded-full flex items-center justify-center mx-auto mb-4">
              <User size={32} className="text-orange-600" />
            </div>
            <h2 className="text-2xl font-bold text-gray-900 mb-2">
              {isAnonymous ? 'Upgrade your account' : 'Sign in to unlock all features'}
            </h2>
            <p className="text-gray-600">
              Get persistent chat history and access to all models
            </p>
          </div>

          {/* Benefits */}
          <div className="space-y-3 mb-6">
            <div className="flex items-start gap-3">
              <Clock className="text-green-600 mt-0.5" size={20} />
              <div className="text-left">
                <p className="font-medium text-gray-900">Permanent chat history</p>
                <p className="text-sm text-gray-600">Your conversations are saved forever</p>
              </div>
            </div>
            <div className="flex items-start gap-3">
              <Sparkles className="text-purple-600 mt-0.5" size={20} />
              <div className="text-left">
                <p className="font-medium text-gray-900">Unlimited access</p>
                <p className="text-sm text-gray-600">No message or session limits</p>
              </div>
            </div>
            <div className="flex items-start gap-3">
              <Shield className="text-blue-600 mt-0.5" size={20} />
              <div className="text-left">
                <p className="font-medium text-gray-900">Account security</p>
                <p className="text-sm text-gray-600">Secure login with Google</p>
              </div>
            </div>
          </div>

          {/* Error message */}
          {error && (
            <div className="mb-4 p-3 bg-red-50 border border-red-200 rounded-lg">
              <p className="text-sm text-red-600">{error}</p>
            </div>
          )}

          {/* Sign In Buttons */}
          <div className="space-y-4">
            <button
              onClick={handleGoogleSignIn}
              disabled={loading || isSigningIn}
              className="w-full flex items-center justify-center gap-3 px-4 py-3 border border-gray-300 rounded-lg hover:bg-gray-50 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {(loading || isSigningIn) ? (
                <div className="animate-spin rounded-full h-5 w-5 border-b-2 border-orange-600"></div>
              ) : (
                <>
                  <svg className="w-5 h-5" viewBox="0 0 24 24">
                    <path
                      fill="#4285F4"
                      d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"
                    />
                    <path
                      fill="#34A853"
                      d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"
                    />
                    <path
                      fill="#FBBC05"
                      d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"
                    />
                    <path
                      fill="#EA4335"
                      d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"
                    />
                  </svg>
                  <span className="text-gray-700 font-medium">Continue with Google</span>
                </>
              )}
            </button>
            
            {isAnonymous && (
              <p className="text-xs text-gray-500 text-center">
                Your current session will be transferred to your Google account
              </p>
            )}
          </div>

          {/* Continue as guest */}
          {!isAnonymous && (
            <button
              onClick={handleContinueAsGuest}
              disabled={loading}
              className="w-full mt-4 text-sm text-gray-600 hover:text-gray-800 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              Continue as guest
            </button>
          )}
        </div>
      </div>
    </>
  );
}