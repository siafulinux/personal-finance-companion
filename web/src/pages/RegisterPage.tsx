import { useMemo, useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Button, Field, Input, Select } from "../components/ui";
import { useAuth } from "../context/AuthContext";
import { AuthLayout } from "./AuthLayout";

function timezoneOptions(): string[] {
  const intl = Intl as unknown as { supportedValuesOf?: (key: string) => string[] };
  const all = intl.supportedValuesOf?.("timeZone") ?? [];
  if (all.length) return all;
  return [
    "America/New_York",
    "America/Chicago",
    "America/Denver",
    "America/Los_Angeles",
    "Europe/London",
    "Europe/Berlin",
    "Asia/Tokyo",
    "Australia/Sydney",
    "UTC",
  ];
}

export function RegisterPage() {
  const { register } = useAuth();
  const navigate = useNavigate();
  const zones = useMemo(timezoneOptions, []);
  const detected = Intl.DateTimeFormat().resolvedOptions().timeZone || "America/New_York";
  const [displayName, setDisplayName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [timezone, setTimezone] = useState(zones.includes(detected) ? detected : "UTC");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const onSubmit = async (event: FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await register({
        email: email.trim(),
        password,
        display_name: displayName.trim(),
        timezone,
      });
      navigate("/onboarding", { replace: true });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to create your account.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <AuthLayout
      title="Create your ledger"
      subtitle="A private account, a few numbers, and a plan you can actually keep."
      footer={
        <>
          Already have an account? <Link to="/login">Sign in</Link>
        </>
      }
    >
      <form onSubmit={onSubmit} className="page-stack" style={{ gap: "0.9rem" }}>
        <Field label="Display name" htmlFor="register-name">
          <Input
            id="register-name"
            required
            maxLength={120}
            value={displayName}
            onChange={(e) => setDisplayName(e.target.value)}
            placeholder="Alex"
          />
        </Field>
        <Field label="Email address" htmlFor="register-email">
          <Input
            id="register-email"
            type="email"
            autoComplete="email"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="you@example.com"
          />
        </Field>
        <Field
          label="Password"
          hint="At least 10 characters, including a letter and a number."
          htmlFor="register-password"
        >
          <Input
            id="register-password"
            type="password"
            autoComplete="new-password"
            required
            minLength={10}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="Choose a strong password"
          />
        </Field>
        <Field label="Timezone" hint="Used for payday, due dates and month boundaries." htmlFor="register-tz">
          <Select id="register-tz" value={timezone} onChange={(e) => setTimezone(e.target.value)}>
            {zones.map((zone) => (
              <option key={zone} value={zone}>
                {zone.replace(/_/g, " ")}
              </option>
            ))}
          </Select>
        </Field>
        {error ? <div className="form-error" role="alert">{error}</div> : null}
        <Button type="submit" loading={busy}>
          Create account
        </Button>
      </form>
      <p className="tiny muted">
        Phase 1 stores data in your own PostgreSQL instance. No bank passwords, ever.
      </p>
    </AuthLayout>
  );
}
