"use client";

import {
  createContext,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

const STORAGE_KEY = "arte_admin_key";

interface AdminAuthContextType {
  apiKey: string | null;
  setApiKey: (key: string) => void;
  logout: () => void;
  isAuthenticated: boolean;
  isReady: boolean;
}

const AdminAuthContext = createContext<AdminAuthContextType | null>(null);

export function AdminAuthProvider({ children }: { children: ReactNode }) {
  const [apiKey, setApiKeyState] = useState<string | null>(null);
  const [isReady, setIsReady] = useState(false);

  useEffect(() => {
    setApiKeyState(window.localStorage.getItem(STORAGE_KEY));
    setIsReady(true);
  }, []);

  const setApiKey = (key: string) => {
    const trimmed = key.trim();
    window.localStorage.setItem(STORAGE_KEY, trimmed);
    setApiKeyState(trimmed);
  };

  const logout = () => {
    window.localStorage.removeItem(STORAGE_KEY);
    setApiKeyState(null);
  };

  const value = useMemo(
    () => ({
      apiKey,
      setApiKey,
      logout,
      isAuthenticated: Boolean(apiKey),
      isReady,
    }),
    [apiKey, isReady],
  );

  return (
    <AdminAuthContext.Provider value={value}>
      {children}
    </AdminAuthContext.Provider>
  );
}

export function useAdminAuth() {
  const context = useContext(AdminAuthContext);
  if (!context) {
    throw new Error("useAdminAuth must be used within AdminAuthProvider");
  }
  return context;
}

export { STORAGE_KEY };
