import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { ApiError, api } from "../lib/api";
import type { Profile } from "../lib/types";

interface AuthContextValue {
  profile: Profile | null;
  loading: boolean;
  error: string | null;
  login: (email: string, password: string) => Promise<void>;
  register: (input: {
    email: string;
    password: string;
    display_name: string;
    timezone: string;
  }) => Promise<void>;
  logout: () => Promise<void>;
  refresh: () => Promise<void>;
  setProfile: (profile: Profile) => void;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [profile, setProfile] = useState<Profile | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      const next = await api.auth.me();
      setProfile(next);
      setError(null);
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        setProfile(null);
      } else {
        setError(err instanceof Error ? err.message : "Unable to load your account.");
      }
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const login = useCallback(async (email: string, password: string) => {
    await api.auth.login({ email, password });
    const next = await api.auth.me();
    setProfile(next);
    setError(null);
  }, []);

  const register = useCallback(
    async (input: { email: string; password: string; display_name: string; timezone: string }) => {
      await api.auth.register(input);
      const next = await api.auth.me();
      setProfile(next);
      setError(null);
    },
    []
  );

  const logout = useCallback(async () => {
    try {
      await api.auth.logout();
    } finally {
      setProfile(null);
    }
  }, []);

  const value = useMemo(
    () => ({ profile, loading, error, login, register, logout, refresh, setProfile }),
    [profile, loading, error, login, register, logout, refresh]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth must be used inside AuthProvider");
  return context;
}
