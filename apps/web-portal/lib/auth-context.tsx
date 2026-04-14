'use client';

import React, { createContext, useContext, useEffect, useState } from 'react';
import type { AuthUser } from './types';

interface AuthCtx {
  user: AuthUser | null;
  setUser: (u: AuthUser | null) => void;
}

const AuthContext = createContext<AuthCtx>({ user: null, setUser: () => {} });

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null);

  useEffect(() => {
    const stored = localStorage.getItem('user');
    if (stored) {
      try {
        setUser(JSON.parse(stored));
      } catch {
        setUser(null);
      }
    }
  }, []);

  return <AuthContext.Provider value={{ user, setUser }}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  return useContext(AuthContext);
}