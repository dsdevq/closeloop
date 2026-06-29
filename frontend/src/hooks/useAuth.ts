import { useState, useEffect } from 'react';
import type { User } from '../types';
import { getToken, storedUser } from '../lib/api';

export function useAuth() {
  const [isAuthenticated, setIsAuthenticated] = useState(Boolean(getToken()));
  const [user, setUser] = useState<User>(storedUser);

  useEffect(() => {
    if (window.location.pathname.endsWith('/login.html') && isAuthenticated) {
      window.history.replaceState(null, '', '/');
    }
  }, [isAuthenticated]);

  async function handleLogin(email: string, password: string) {
    const response = await fetch('/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, password }),
    });
    if (!response.ok) {
      const data = await response.json().catch(() => ({}));
      throw new Error(data.detail || 'Invalid email or password');
    }
    const data = await response.json();
    localStorage.setItem('access_token', data.access_token);
    localStorage.setItem('refresh_token', data.refresh_token);
    localStorage.setItem('current_user', JSON.stringify(data.user));
    setUser(data.user);
    setIsAuthenticated(true);
  }

  async function logout() {
    const refresh = localStorage.getItem('refresh_token');
    if (refresh) {
      await fetch('/auth/logout', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ refresh_token: refresh }),
      }).catch(() => undefined);
    }
    localStorage.removeItem('access_token');
    localStorage.removeItem('refresh_token');
    localStorage.removeItem('current_user');
    setIsAuthenticated(false);
    window.history.replaceState(null, '', '/login.html');
  }

  return { isAuthenticated, user, handleLogin, logout };
}
