// زمینه احراز هویت
import React, { createContext, useContext, useEffect, useState } from 'react';
import { api, UserInfo } from '../api/client';

interface AuthState {
  user: UserInfo | null;
  loading: boolean;
  login: (username: string, password: string) => Promise<void>;
  logout: () => void;
  hasPerm: (perm: string) => boolean;
}

const AuthContext = createContext<AuthState>({
  user: null,
  loading: true,
  login: async () => {},
  logout: () => {},
  hasPerm: () => false,
});

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<UserInfo | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    // فاز ۵: توکن بازگشتی از ورود سازمانی OIDC (?oidc_token=...)
    const url = new URL(window.location.href);
    const oidcToken = url.searchParams.get('oidc_token');
    if (oidcToken) {
      localStorage.setItem('bpms_token', oidcToken);
      url.searchParams.delete('oidc_token');
      window.history.replaceState({}, '', url.pathname + (url.searchParams.toString() ? `?${url.searchParams}` : ''));
    }
    const token = localStorage.getItem('bpms_token');
    if (!token) { setLoading(false); return; }
    api.get('/auth/me')
      .then((r) => setUser(r.data))
      .catch(() => localStorage.removeItem('bpms_token'))
      .finally(() => setLoading(false));
  }, []);

  const login = async (username: string, password: string) => {
    const r = await api.post('/auth/login', { username, password });
    localStorage.setItem('bpms_token', r.data.access_token);
    setUser(r.data.user);
  };

  const logout = () => {
    localStorage.removeItem('bpms_token');
    setUser(null);
    window.location.href = '/login';
  };

  const hasPerm = (perm: string): boolean => {
    if (!user) return false;
    if (user.is_superadmin) return true;
    for (const r of user.roles) {
      const perms = r.permissions || [];
      if (perms.includes('*') || perms.includes(perm)) return true;
      for (const p of perms) {
        if (p.endsWith('.*') && perm.startsWith(p.slice(0, -1))) return true;
      }
    }
    return false;
  };

  return (
    <AuthContext.Provider value={{ user, loading, login, logout, hasPerm }}>
      {children}
    </AuthContext.Provider>
  );
}

export const useAuth = () => useContext(AuthContext);
