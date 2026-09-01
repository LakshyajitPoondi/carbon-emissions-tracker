import { useState } from "react";
import type { FormEvent } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import type { Location } from "react-router-dom";
import { ErrorBanner } from "../components/ErrorBanner";
import { useAuth } from "../context/AuthContext";
import { ENABLE_DEMO_ACCESS } from "../api/config";

type Mode = "login" | "register";

const DEMO_PASSWORD = "DemoPass123!";
const DEMO_ACCOUNTS = [
  { label: "Explore as Owner/Admin", email: "admin-demo@gmail.com" },
  { label: "Explore as Employee", email: "employee-demo@gmail.com" },
] as const;

interface LocationState {
  from?: Location;
}

export function AuthPage() {
  const { login, register, submitting } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const redirectTo = (location.state as LocationState | null)?.from?.pathname ?? "/";

  const [mode, setMode] = useState<Mode>("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<unknown>(null);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      if (mode === "login") {
        await login(email, password);
        navigate(redirectTo, { replace: true });
      } else {
        await register(email, password);
        // A new account has no membership yet. Always land on Setup so the
        // create-or-join choice is visible instead of returning to a data
        // page that cannot work without an organization.
        navigate("/", { replace: true });
      }
    } catch (err) {
      setError(err);
    }
  }

  function toggleMode() {
    setMode((m) => (m === "login" ? "register" : "login"));
    setError(null);
  }

  function fillDemoCredentials(demoEmail: string) {
    setMode("login");
    setEmail(demoEmail);
    setPassword(DEMO_PASSWORD);
    setError(null);
  }

  return (
    <main className="auth-page">
      <section className="card auth-card">
        <div className="auth-card__brand">
          <span className="auth-card__mark" aria-hidden="true">C</span>
          <span>Carbon Emissions Tracker</span>
        </div>
        <p className="auth-card__tagline">
          Measure smarter. Reduce emissions. Report with confidence.
        </p>
        <h1 className="auth-card__heading">
          {mode === "login" ? "Sign In" : "Create Account"}
        </h1>

        <form className="auth-form" onSubmit={handleSubmit}>
          <div className="field">
            <label htmlFor="auth-email">Email</label>
            <input
              id="auth-email"
              type="email"
              autoComplete="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
              placeholder="you@example.com"
            />
          </div>
          <div className="field">
            <label htmlFor="auth-password">Password</label>
            <input
              id="auth-password"
              type="password"
              autoComplete={mode === "login" ? "current-password" : "new-password"}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              minLength={mode === "register" ? 8 : undefined}
              placeholder={mode === "register" ? "At least 8 characters" : "Your password"}
            />
          </div>
          <button type="submit" className="auth-form__submit" disabled={submitting}>
            {submitting
              ? mode === "login"
                ? "Signing in…"
                : "Creating account…"
              : mode === "login"
                ? "Sign In"
                : "Create Account"}
          </button>
          {error !== null && <ErrorBanner error={error} />}
        </form>

        <p className="auth-card__switch">
          {mode === "login" ? "Don't have an account?" : "Already have an account?"}{" "}
          <button type="button" className="link-button" onClick={toggleMode}>
            {mode === "login" ? "Register" : "Sign In"}
          </button>
        </p>
      </section>

      {mode === "login" && ENABLE_DEMO_ACCESS && (
        <aside className="demo-access" aria-labelledby="demo-access-title">
          <div>
            <h2 id="demo-access-title">Demo Access</h2>
            <p>Choose a role to fill the sign-in form. You stay in control of submitting it.</p>
          </div>
          <div className="demo-access__actions">
            {DEMO_ACCOUNTS.map((account) => (
              <button
                type="button"
                className="demo-access__button"
                key={account.email}
                onClick={() => fillDemoCredentials(account.email)}
              >
                {account.label}
              </button>
            ))}
          </div>
        </aside>
      )}
    </main>
  );
}
