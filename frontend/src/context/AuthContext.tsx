import { createContext, useCallback, useContext, useEffect, useState } from "react";
import type { ReactNode } from "react";
import { apiClient } from "../api";
import { clearToken, getToken, setToken } from "../api/authToken";
import { UNAUTHORIZED_EVENT } from "../api/realClient";

const EMAIL_KEY = "cfp.auth.email";

function loadStoredEmail(): string | null {
  try {
    return localStorage.getItem(EMAIL_KEY);
  } catch {
    return null;
  }
}

function storeEmail(email: string | null): void {
  try {
    if (email) localStorage.setItem(EMAIL_KEY, email);
    else localStorage.removeItem(EMAIL_KEY);
  } catch {
    // ignore
  }
}

interface AuthState {
  isAuthenticated: boolean;
  email: string | null;
  submitting: boolean;
  login: (email: string, password: string) => Promise<void>;
  register: (email: string, password: string) => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [token, setTokenState] = useState<string | null>(() => getToken());
  const [email, setEmail] = useState<string | null>(() => loadStoredEmail());
  const [submitting, setSubmitting] = useState(false);

  // A 401 from any request (real backend only — the mock client never
  // returns one after a successful login) means the token is dead; drop
  // local auth state so route protection bounces the user to /login.
  useEffect(() => {
    function handleUnauthorized() {
      setTokenState(null);
      setEmail(null);
      storeEmail(null);
    }
    window.addEventListener(UNAUTHORIZED_EVENT, handleUnauthorized);
    return () => window.removeEventListener(UNAUTHORIZED_EVENT, handleUnauthorized);
  }, []);

  const login = useCallback(async (loginEmail: string, password: string) => {
    setSubmitting(true);
    try {
      const res = await apiClient.login({ email: loginEmail, password });
      setToken(res.access_token);
      setTokenState(res.access_token);
      setEmail(loginEmail);
      storeEmail(loginEmail);
    } finally {
      setSubmitting(false);
    }
  }, []);

  const register = useCallback(
    async (registerEmail: string, password: string) => {
      setSubmitting(true);
      try {
        await apiClient.register({ email: registerEmail, password });
      } finally {
        setSubmitting(false);
      }
      // Registration doesn't return a token (per docs/api-contract.md) — log
      // in immediately after so signup is a single user-facing step.
      await login(registerEmail, password);
    },
    [login],
  );

  const logout = useCallback(() => {
    clearToken();
    setTokenState(null);
    setEmail(null);
    storeEmail(null);
  }, []);

  return (
    <AuthContext.Provider
      value={{ isAuthenticated: token !== null, email, submitting, login, register, logout }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within an AuthProvider");
  return ctx;
}
