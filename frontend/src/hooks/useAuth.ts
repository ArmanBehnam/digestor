/**
 * Authentication hook - replaces Supabase Auth hooks.
 * Works with AWS Cognito via FastAPI backend.
 */

import { useState, useEffect, useCallback, createContext, useContext } from 'react';
import apiClient from '@/lib/apiClient';

interface User {
  id: string;
  email: string;
  full_name: string;
  role: string;
  organization?: string;
  groups: string[];
}

interface AuthState {
  user: User | null;
  isLoading: boolean;
  isAuthenticated: boolean;
}

interface AuthContextType extends AuthState {
  login: (email: string, password: string) => Promise<any>;
  register: (email: string, password: string, fullName: string, org?: string) => Promise<void>;
  logout: () => Promise<void>;
  resetPassword: (email: string) => Promise<void>;
  respondChallenge: (session: string, email: string, newPassword: string) => Promise<void>;
  refreshUser: () => Promise<void>;
}

const AuthContext = createContext<AuthContextType | null>(null);

export function useAuth(): AuthContextType {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
}

export function useAuthProvider(): AuthContextType {
  const [state, setState] = useState<AuthState>({
    user: null,
    isLoading: true,
    isAuthenticated: false,
  });

  const refreshUser = useCallback(async () => {
    const token = localStorage.getItem('access_token');
    if (!token) {
      setState({ user: null, isLoading: false, isAuthenticated: false });
      return;
    }

    try {
      const user = await apiClient.getMe();
      setState({ user, isLoading: false, isAuthenticated: true });
    } catch {
      localStorage.removeItem('access_token');
      localStorage.removeItem('id_token');
      localStorage.removeItem('refresh_token');
      setState({ user: null, isLoading: false, isAuthenticated: false });
    }
  }, []);

  useEffect(() => {
    refreshUser();
  }, [refreshUser]);

  const login = useCallback(async (email: string, password: string) => {
    const response = await apiClient.login(email, password);

    // Handle NEW_PASSWORD_REQUIRED challenge (migrated users)
    if (response.challenge === 'NEW_PASSWORD_REQUIRED') {
      return response; // Caller handles challenge UI
    }

    // Store tokens
    localStorage.setItem('access_token', response.access_token);
    localStorage.setItem('id_token', response.id_token);
    localStorage.setItem('refresh_token', response.refresh_token);

    await refreshUser();
    return response;
  }, [refreshUser]);

  const register = useCallback(async (
    email: string, password: string, fullName: string, org?: string
  ) => {
    await apiClient.register(email, password, fullName, org);
  }, []);

  const logout = useCallback(async () => {
    await apiClient.logout();
    setState({ user: null, isLoading: false, isAuthenticated: false });
  }, []);

  const resetPassword = useCallback(async (email: string) => {
    await apiClient.resetPassword(email);
  }, []);

  const respondChallenge = useCallback(async (
    session: string, email: string, newPassword: string
  ) => {
    const response = await apiClient.respondChallenge(session, email, newPassword);
    localStorage.setItem('access_token', response.access_token);
    localStorage.setItem('id_token', response.id_token);
    localStorage.setItem('refresh_token', response.refresh_token);
    await refreshUser();
  }, [refreshUser]);

  return {
    ...state,
    login,
    register,
    logout,
    resetPassword,
    respondChallenge,
    refreshUser,
  };
}

export { AuthContext };
export type { User, AuthContextType };
