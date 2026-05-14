import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react';
import { apiFetch, setAccessToken } from '../utils/apiClient';
import type { AuthUser, LoginResponse } from './types';

interface AuthContextValue {
  user: AuthUser | null;
  isBootstrapping: boolean;
  login: (username: string, password: string) => Promise<void>;
  register: (payload: { username: string; password: string; email?: string }) => Promise<void>;
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [isBootstrapping, setIsBootstrapping] = useState(true);

  const loadCurrentUser = useCallback(async () => {
    try {
      const refreshed = await apiFetch<{ access_token: string }>('/api/auth/refresh', {
        method: 'POST',
        skipAuthRefresh: true,
      });
      setAccessToken(refreshed.access_token);
      const payload = await apiFetch<{ user: AuthUser }>('/api/auth/me');
      setUser(payload.user);
    } catch {
      setAccessToken(null);
      setUser(null);
    } finally {
      setIsBootstrapping(false);
    }
  }, []);

  useEffect(() => {
    void loadCurrentUser();
  }, [loadCurrentUser]);

  useEffect(() => {
    const handleLogout = () => {
      setAccessToken(null);
      setUser(null);
    };
    window.addEventListener('auth:logout', handleLogout);
    return () => window.removeEventListener('auth:logout', handleLogout);
  }, []);

  const login = useCallback(async (username: string, password: string) => {
    const payload = await apiFetch<LoginResponse>('/api/auth/login', {
      method: 'POST',
      body: JSON.stringify({ username, password }),
      skipAuthRefresh: true,
    });
    setAccessToken(payload.access_token);
    setUser(payload.user);
  }, []);

  const register = useCallback(async (payload: { username: string; password: string; email?: string }) => {
    await apiFetch('/api/auth/register', {
      method: 'POST',
      body: JSON.stringify(payload),
      skipAuthRefresh: true,
    });
  }, []);

  const logout = useCallback(async () => {
    try {
      await apiFetch('/api/auth/logout', { method: 'POST', skipAuthRefresh: true });
    } finally {
      setAccessToken(null);
      setUser(null);
    }
  }, []);

  const value = useMemo(
    () => ({ user, isBootstrapping, login, register, logout }),
    [isBootstrapping, login, logout, register, user],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within AuthProvider');
  }
  return context;
}
