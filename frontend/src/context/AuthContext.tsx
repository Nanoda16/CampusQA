import { createContext, useContext, useState, useEffect, useCallback, type ReactNode } from 'react';
import { setTokenGetter } from '../services/api';

interface User {
  id?: number;
  username?: string;
  nickname?: string;
  role?: string;
  [key: string]: any;
}

interface AuthContextValue {
  user: User | null;
  token: string | null;
  isAuthenticated: boolean;
  login: (token: string, user: User) => void;
  logout: () => void;
}

const AuthContext = createContext<AuthContextValue | null>(null);

const STORAGE_KEYS = {
  token: 'token',
  user: 'user',
} as const;

function loadFromStorage() {
  const token = localStorage.getItem(STORAGE_KEYS.token);
  const userStr = localStorage.getItem(STORAGE_KEYS.user);
  return {
    token,
    user: userStr ? (JSON.parse(userStr) as User) : null,
  };
}

function saveToStorage(token: string, user: User) {
  localStorage.setItem(STORAGE_KEYS.token, token);
  localStorage.setItem(STORAGE_KEYS.user, JSON.stringify(user));
}

function clearStorage() {
  localStorage.removeItem(STORAGE_KEYS.token);
  localStorage.removeItem(STORAGE_KEYS.user);
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [token, setToken] = useState<string | null>(null);
  const [user, setUser] = useState<User | null>(null);
  // Track if initial restore has happened
  const [initialized, setInitialized] = useState(false);

  // Restore from localStorage on mount
  useEffect(() => {
    const stored = loadFromStorage();
    if (stored.token) {
      setToken(stored.token);
      setUser(stored.user);
    }
    setInitialized(true);
  }, []);

  // Sync token/api getter when token changes (updated after restore + every login/logout)
  useEffect(() => {
    if (initialized) {
      setTokenGetter(() => token);
    }
  }, [token, initialized]);

  const login = useCallback((newToken: string, newUser: User) => {
    setToken(newToken);
    setUser(newUser);
    saveToStorage(newToken, newUser);
  }, []);

  const logout = useCallback(() => {
    setToken(null);
    setUser(null);
    clearStorage();
  }, []);

  const value: AuthContextValue = {
    user,
    token,
    isAuthenticated: !!token,
    login,
    logout,
  };

  // Don't render children until we've restored auth state
  // to avoid flash of unauthenticated content on refresh
  if (!initialized) {
    return null;
  }

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return ctx;
}
