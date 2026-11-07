import { useState, type FormEvent } from "react";
import { Button, Field, Input } from "../components/ui";
import { api } from "../lib/api";
import { AuthLayout } from "./AuthLayout";

/**
 * First-run wizard. The server only shows this while it has no accounts, and the
 * API refuses a second attempt once this succeeds — so it is not a reusable
 * "create an admin" form.
 */
export function SetupPage() {
  const [serverName, setServerName] = useState("Home Finance");
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [registration, setRegistration] = useState(false);
  const [publicUrl, setPublicUrl] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const onSubmit = async (event: FormEvent) => {
    event.preventDefault();
    setError(null);
    if (password !== confirm) {
      setError("The two passwords do not match.");
      return;
    }
    if (password.length < 10) {
      setError("Choose a password with at least 10 characters.");
      return;
    }
    setBusy(true);
    try {
      await api.server.setup({
        server_name: serverName.trim(),
        admin_name: name.trim(),
        admin_email: email.trim(),
        admin_password: password,
        registration_enabled: registration,
        public_base_url: publicUrl.trim() || null,
      });
      // The response set the session cookies; a full load re-reads the server
      // state and drops straight into the app.
      window.location.assign("/");
    } catch (err) {
      setError(err instanceof Error ? err.message : "The server could not be set up.");
      setBusy(false);
    }
  };

  return (
    <AuthLayout
      title="Set up this server"
      subtitle="This installation has no accounts yet. Create its owner account now — whoever finishes this first controls the server."
      footer={
        <span className="tiny">
          Running on your own hardware. Your ledger never leaves this machine.
        </span>
      }
    >
      <form onSubmit={onSubmit} className="page-stack" style={{ gap: "0.9rem" }}>
        <Field label="Server name" htmlFor="setup-server-name" hint="Shown in the web app and on the phone.">
          <Input
            id="setup-server-name"
            required
            maxLength={120}
            value={serverName}
            onChange={(e) => setServerName(e.target.value)}
            placeholder="Home Finance"
          />
        </Field>

        <Field label="Your name" htmlFor="setup-name">
          <Input
            id="setup-name"
            required
            maxLength={120}
            autoComplete="name"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="Alex Morgan"
          />
        </Field>

        <Field label="Email address" htmlFor="setup-email">
          <Input
            id="setup-email"
            type="email"
            required
            autoComplete="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="you@example.com"
          />
        </Field>

        <Field label="Password" htmlFor="setup-password" hint="At least 10 characters.">
          <Input
            id="setup-password"
            type="password"
            required
            autoComplete="new-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="••••••••••"
          />
        </Field>

        <Field label="Confirm password" htmlFor="setup-confirm">
          <Input
            id="setup-confirm"
            type="password"
            required
            autoComplete="new-password"
            value={confirm}
            onChange={(e) => setConfirm(e.target.value)}
            placeholder="••••••••••"
          />
        </Field>

        <label className="checkbox-row">
          <input
            type="checkbox"
            checked={registration}
            onChange={(e) => setRegistration(e.target.checked)}
          />
          <span>
            Allow other people to create accounts on this server.
            <span className="tiny" style={{ display: "block" }}>
              Leave this off unless you share the server. You can change it later.
            </span>
          </span>
        </label>

        <Field
          label="Public address (optional)"
          htmlFor="setup-public-url"
          hint="Set this if phones reach the server through a domain or tunnel, e.g. https://finance.example.com"
        >
          <Input
            id="setup-public-url"
            value={publicUrl}
            onChange={(e) => setPublicUrl(e.target.value)}
            placeholder="https://finance.example.com"
          />
        </Field>

        {error && <p className="form-error">{error}</p>}

        <Button type="submit" disabled={busy}>
          {busy ? "Setting up…" : "Create administrator and finish"}
        </Button>
      </form>
    </AuthLayout>
  );
}
