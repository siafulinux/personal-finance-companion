import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useAuth } from "../context/AuthContext";
import { api } from "../lib/api";
import type { PairingCode, ServerSettingsView } from "../lib/types";
import {
  Badge,
  Button,
  Card,
  ErrorBanner,
  Field,
  Input,
  LoadingBlock,
  PageHeader,
} from "../components/ui";

function CopyRow({ label, value }: { label: string; value: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <div className="copy-row">
      <div>
        <span className="field__label">{label}</span>
        <p className="mono tiny" style={{ margin: 0 }}>{value}</p>
      </div>
      <Button
        variant="ghost"
        size="sm"
        onClick={async () => {
          try {
            await navigator.clipboard.writeText(value);
            setCopied(true);
            window.setTimeout(() => setCopied(false), 1500);
          } catch {
            setCopied(false);
          }
        }}
      >
        {copied ? "Copied" : "Copy"}
      </Button>
    </div>
  );
}

function SettingsForm({
  settings,
  onSaved,
}: {
  settings: ServerSettingsView;
  onSaved: () => void;
}) {
  const [name, setName] = useState(settings.server_name);
  const [registration, setRegistration] = useState(settings.registration_enabled);
  const [publicUrl, setPublicUrl] = useState(settings.public_base_url ?? "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  const save = async () => {
    setBusy(true);
    setError(null);
    setSaved(false);
    try {
      await api.server.updateSettings({
        server_name: name.trim(),
        registration_enabled: registration,
        public_base_url: publicUrl.trim() || null,
      });
      setSaved(true);
      onSaved();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save these settings.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="page-stack" style={{ gap: "0.9rem" }}>
      <Field label="Server name" htmlFor="server-name">
        <Input
          id="server-name"
          value={name}
          maxLength={120}
          onChange={(e) => setName(e.target.value)}
        />
      </Field>
      <Field
        label="Public address"
        htmlFor="server-public-url"
        hint="Leave empty to advertise whatever address the request arrived on. Set it when phones reach this server through a domain or tunnel."
      >
        <Input
          id="server-public-url"
          value={publicUrl}
          onChange={(e) => setPublicUrl(e.target.value)}
          placeholder="https://finance.example.com"
        />
      </Field>
      <label className="checkbox-row">
        <input
          type="checkbox"
          checked={registration}
          onChange={(e) => setRegistration(e.target.checked)}
        />
        <span>
          Allow new accounts to be created.
          <span className="tiny" style={{ display: "block" }}>
            When off, only the account that created this server exists. Turn it on to invite
            somebody, then turn it off again.
          </span>
        </span>
      </label>
      {error && <p className="form-error">{error}</p>}
      {saved && <p className="tiny">Saved.</p>}
      <Button onClick={save} disabled={busy}>
        {busy ? "Saving…" : "Save server settings"}
      </Button>
    </div>
  );
}

export function ServerPage() {
  const { profile } = useAuth();
  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ["server-settings"],
    queryFn: api.server.settings,
  });
  const [pairing, setPairing] = useState<PairingCode | null>(null);
  const [pairBusy, setPairBusy] = useState(false);
  const [pairError, setPairError] = useState<string | null>(null);

  const createPairing = async () => {
    setPairBusy(true);
    setPairError(null);
    try {
      setPairing(await api.server.createPairing(profile?.user.display_name));
    } catch (err) {
      setPairError(err instanceof Error ? err.message : "Could not create a pairing code.");
    } finally {
      setPairBusy(false);
    }
  };

  if (isLoading) return <LoadingBlock label="Reading this server's configuration" />;
  if (error) return <ErrorBanner message={(error as Error).message} onRetry={() => void refetch()} />;
  if (!data) return null;

  const { server, settings } = data;

  return (
    <div className="page-stack">
      <PageHeader
        eyebrow="This server"
        title={server.server_name}
        description="Everything the Android app and the web app need in order to reach this installation. Nothing here is secret."
        actions={<Badge tone={server.status === "ok" ? "positive" : "warning"}>{server.status}</Badge>}
      />

      <Card>
        <h2 style={{ fontSize: "1.05rem", marginBottom: "0.25rem" }}>Connection</h2>
        <p className="tiny muted" style={{ marginBottom: "0.5rem" }}>
          Give these addresses to any client you want to connect.
        </p>
        <CopyRow label="Web application" value={server.web_url} />
        <CopyRow label="API base URL" value={server.api_base_url} />
        <CopyRow label="Server version" value={`${server.version} (API v${server.api_version})`} />
        <CopyRow label="Release tag" value={server.release_tag} />
        <p className="tiny" style={{ marginTop: "0.8rem" }}>
          On a home network the web address is what you type in a browser. From a phone on the
          same network, replace <span className="mono">localhost</span> with this machine's LAN
          address. Over the internet, use your domain and HTTPS.
        </p>
      </Card>

      <Card>
        <h2 style={{ fontSize: "1.05rem", marginBottom: "0.25rem" }}>Connect the Android app</h2>
        <p className="tiny muted" style={{ marginBottom: "0.9rem" }}>
          Open Settings → Server in the app and enter the API base URL above, or redeem a
          one-time pairing code.
        </p>
        {settings.is_admin ? (
          <>
            <Button onClick={createPairing} disabled={pairBusy}>
              {pairBusy ? "Creating…" : "Create a pairing code"}
            </Button>
            {pairError && <p className="form-error">{pairError}</p>}
            {pairing && (
              <div style={{ marginTop: "1rem" }}>
                <CopyRow label="Pairing code" value={pairing.token} />
                <CopyRow label="Pairing link" value={pairing.pairing_url} />
                <p className="tiny">
                  Valid for {pairing.ttl_minutes} minutes and once only. The code is not a
                  password: it only tells the app which server to use, and signing in still needs
                  your own credentials.
                </p>
              </div>
            )}
          </>
        ) : (
          <p className="tiny">
            Ask the server administrator for a pairing code, or enter the API base URL above
            yourself.
          </p>
        )}
      </Card>

      {settings.is_admin ? (
        <Card>
          <h2 style={{ fontSize: "1.05rem", marginBottom: "0.25rem" }}>Server settings</h2>
          <p className="tiny muted" style={{ marginBottom: "0.9rem" }}>
            Only the account that set up this server can change these.
          </p>
          <SettingsForm
            key={`${settings.server_name}|${settings.registration_enabled}|${settings.public_base_url ?? ""}`}
            settings={settings}
            onSaved={() => void refetch()}
          />
        </Card>
      ) : null}

      <Card>
        <h2 style={{ fontSize: "1.05rem", marginBottom: "0.75rem" }}>Security notes</h2>
        <ul className="tiny" style={{ margin: 0, paddingLeft: "1.1rem", lineHeight: 1.7 }}>
          <li>
            The database has no published port; only this app's HTTP port is reachable from the
            network.
          </li>
          <li>
            Plain HTTP is only appropriate on a network you trust. Before exposing this server to
            the internet, put it behind HTTPS and set the deployment to production mode so
            session cookies are marked Secure.
          </li>
          <li>
            Registration is currently {server.registration_enabled ? "open to anyone who can reach this server" : "closed"}.
          </li>
        </ul>
      </Card>
    </div>
  );
}
