import { useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Button, Field, Input } from "../components/ui";
import { useAuth } from "../context/AuthContext";
import { AuthLayout } from "./AuthLayout";

export function LoginPage() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const onSubmit = async (event: FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await login(email.trim(), password);
      navigate("/", { replace: true });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to sign in.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <AuthLayout
      title="Welcome back"
      subtitle="Sign in to see what is safe to spend today."
      footer={
        <>
          New here? <Link to="/register">Create your ledger</Link>
        </>
      }
    >
      <form onSubmit={onSubmit} className="page-stack" style={{ gap: "0.9rem" }}>
        <Field label="Email address" htmlFor="login-email">
          <Input
            id="login-email"
            type="email"
            autoComplete="email"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="you@example.com"
          />
        </Field>
        <Field label="Password" htmlFor="login-password">
          <Input
            id="login-password"
            type="password"
            autoComplete="current-password"
            required
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="••••••••••"
          />
        </Field>
        {error ? <div className="form-error" role="alert">{error}</div> : null}
        <Button type="submit" loading={busy}>
          Sign in
        </Button>
      </form>
      <p className="tiny muted">
        Demo data is clearly flagged. Seed it with <code>pfc seed-demo</code> (credentials in the
        README) and remove it at any time with <code>pfc seed-demo --remove</code>.
      </p>
    </AuthLayout>
  );
}
