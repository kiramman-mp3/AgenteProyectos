import { createContext, ReactNode, useCallback, useContext, useEffect, useState } from 'react';

import { clearSession, loadSession, login as apiLogin, Session, setUnauthorizedHandler, updateSession } from './api';

type AuthState = {
  session: Session | null;
  loading: boolean;
  login: (server: string, username: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  canDecide: boolean;
  passwordChanged: () => Promise<void>;
};

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<Session | null>(null);
  const [loading, setLoading] = useState(true);

  const logout = useCallback(async () => {
    await clearSession();
    setSession(null);
  }, []);

  useEffect(() => {
    setUnauthorizedHandler(() => void logout());
    loadSession().then(setSession).finally(() => setLoading(false));
  }, [logout]);

  const login = useCallback(async (server: string, username: string, password: string) => {
    setSession(await apiLogin(server, username, password));
  }, []);

  const passwordChanged = useCallback(async () => {
    setSession(await updateSession({ must_change_password: false }));
  }, []);

  const canDecide = session?.role === 'gestor' || session?.role === 'admin';

  return (
    <AuthContext.Provider value={{ session, loading, login, logout, canDecide, passwordChanged }}>{children}</AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth debe usarse dentro de AuthProvider');
  return ctx;
}
