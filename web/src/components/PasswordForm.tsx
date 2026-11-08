import { useState, type FormEvent } from "react";
import { Button, Field, Input } from "./ui";

/**
 * Change-password form. It owns only what is a form concern — that the two new
 * entries match, and what to say afterwards. The server decides whether the current
 * password is right and whether the new one satisfies policy, so those messages are
 * shown verbatim instead of being guessed at here.
 */
export function PasswordForm({
  onSubmit,
}: {
  onSubmit: (currentPassword: string, newPassword: string) => Promise<void>;
}) {
  const [form, setForm] = useState({ current: "", next: "", confirm: "" });
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const [busy, setBusy] = useState(false);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setError(null);
    setSaved(false);
    if (form.next !== form.confirm) {
      setError("The new passwords do not match.");
      return;
    }
    setBusy(true);
    try {
      await onSubmit(form.current, form.next);
      // The server reissued this session; the fields must not keep the secret.
      setForm({ current: "", next: "", confirm: "" });
      setSaved(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to change your password.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <form className="page-stack" style={{ gap: "0.8rem" }} onSubmit={submit}>
      <div className="form-grid">
        <Field label="Current password" htmlFor="pw-current">
          <Input
            id="pw-current"
            type="password"
            autoComplete="current-password"
            value={form.current}
            onChange={(e) => setForm({ ...form, current: e.target.value })}
          />
        </Field>
        <Field
          label="New password"
          hint="At least 8 characters, with a letter and a number."
          htmlFor="pw-new"
        >
          <Input
            id="pw-new"
            type="password"
            autoComplete="new-password"
            value={form.next}
            onChange={(e) => setForm({ ...form, next: e.target.value })}
          />
        </Field>
        <Field label="Confirm new password" htmlFor="pw-confirm">
          <Input
            id="pw-confirm"
            type="password"
            autoComplete="new-password"
            value={form.confirm}
            onChange={(e) => setForm({ ...form, confirm: e.target.value })}
          />
        </Field>
      </div>
      <div className="form-actions">
        {saved ? (
          <span className="tiny muted">Password changed. Other devices were signed out.</span>
        ) : null}
        <Button
          type="submit"
          loading={busy}
          disabled={!form.current || !form.next || !form.confirm}
        >
          Change password
        </Button>
      </div>
      {error ? (
        <div className="form-error" role="alert">
          {error}
        </div>
      ) : null}
    </form>
  );
}
