import type { User } from '../types';

export function getToken(): string | null {
  return localStorage.getItem('access_token');
}

export function storedUser(): User {
  try {
    return JSON.parse(localStorage.getItem('current_user') || '{}') as User;
  } catch {
    return {};
  }
}

export async function apiFetch(path: string, init: RequestInit = {}): Promise<Response> {
  const headers = new Headers(init.headers || {});
  headers.set('Content-Type', headers.get('Content-Type') || 'application/json');
  const token = getToken();
  if (token) headers.set('Authorization', `Bearer ${token}`);

  const response = await fetch(path, { ...init, headers });
  if (response.status === 401) {
    localStorage.removeItem('access_token');
    localStorage.removeItem('refresh_token');
    localStorage.removeItem('current_user');
    window.location.replace('/login.html');
  }
  return response;
}
