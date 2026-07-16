import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import { renderHook, act, waitFor } from '@testing-library/react';
import { AuthProvider, useAuth } from '../context/AuthContext';
import type { ReactNode } from 'react';

function createWrapper() {
  return function Wrapper({ children }: { children: ReactNode }) {
    return <AuthProvider>{children}</AuthProvider>;
  };
}

describe('AuthContext', () => {
  beforeEach(() => {
    localStorage.clear();
  });

  afterEach(() => {
    localStorage.clear();
  });

  it('throws when useAuth is used outside AuthProvider', () => {
    expect(() => renderHook(() => useAuth())).toThrow(
      'useAuth must be used within an AuthProvider'
    );
  });

  it('provides null user and token initially', async () => {
    const { result } = renderHook(() => useAuth(), { wrapper: createWrapper() });

    await waitFor(() => {
      expect(result.current.token).toBeNull();
      expect(result.current.user).toBeNull();
      expect(result.current.isAuthenticated).toBe(false);
    });
  });

  it('sets token and user on login', async () => {
    const { result } = renderHook(() => useAuth(), { wrapper: createWrapper() });

    await act(async () => {
      result.current.login('test-token', { username: 'testuser', role: 'user' });
    });

    expect(result.current.token).toBe('test-token');
    expect(result.current.user).toEqual({ username: 'testuser', role: 'user' });
    expect(result.current.isAuthenticated).toBe(true);
  });

  it('persists token and user to localStorage on login', async () => {
    const { result } = renderHook(() => useAuth(), { wrapper: createWrapper() });

    await act(async () => {
      result.current.login('persist-token', { username: 'persist-user' });
    });

    expect(localStorage.getItem('token')).toBe('persist-token');
    expect(JSON.parse(localStorage.getItem('user')!)).toEqual({
      username: 'persist-user',
    });
  });

  it('clears token and user on logout', async () => {
    // Pre-populate localStorage to simulate logged-in state
    localStorage.setItem('token', 'test-token');
    localStorage.setItem('user', JSON.stringify({ username: 'testuser' }));

    const { result } = renderHook(() => useAuth(), { wrapper: createWrapper() });

    // Wait for restore
    await waitFor(() => {
      expect(result.current.isAuthenticated).toBe(true);
    });

    await act(async () => {
      result.current.logout();
    });

    expect(result.current.token).toBeNull();
    expect(result.current.user).toBeNull();
    expect(result.current.isAuthenticated).toBe(false);
    expect(localStorage.getItem('token')).toBeNull();
    expect(localStorage.getItem('user')).toBeNull();
  });

  it('restores auth state from localStorage on mount', async () => {
    localStorage.setItem('token', 'restored-token');
    localStorage.setItem('user', JSON.stringify({ username: 'restored-user' }));

    const { result } = renderHook(() => useAuth(), { wrapper: createWrapper() });

    await waitFor(() => {
      expect(result.current.token).toBe('restored-token');
      expect(result.current.user).toEqual({ username: 'restored-user' });
      expect(result.current.isAuthenticated).toBe(true);
    });
  });

  it('provides stable login/logout callbacks across re-renders', () => {
    const { result, rerender } = renderHook(() => useAuth(), {
      wrapper: createWrapper(),
    });

    const login1 = result.current.login;
    const logout1 = result.current.logout;

    rerender();

    expect(result.current.login).toBe(login1);
    expect(result.current.logout).toBe(logout1);
  });
});
