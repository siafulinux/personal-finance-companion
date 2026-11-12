import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../lib/api";
import { formatDate } from "../lib/format";
import type {
  CoverageReport,
  ProviderAdmin,
  ProviderCredentialField,
  ProviderOverview,
} from "../lib/types";
import {
  Badge,
  Button,
  Card,
  ErrorBanner,
  Field,
  Input,
  LoadingBlock,
  PageHeader,
  Select,
  Textarea,
} from "../components/ui";

function statusBadge(provider: ProviderAdmin) {
  if (!provider.configured) return <Badge tone="warning">Needs credentials</Badge>;
  if (!provider.enabled) return <Badge tone="neutral">Disabled</Badge>;
  if (!provider.last_test?.at) return <Badge tone="warning">Untested</Badge>;
  return <Badge tone="positive">Ready</Badge>;
}

/**
 * Why a switched-on provider still cannot connect anybody, or null when it can.
 *
 * Both cases look configured on screen -- the switch is on -- but the server has
 * nothing usable, and the failure only surfaces when a user tries to link an
 * institution and is told no provider supports it.
 */
function connectionBlocker(provider: ProviderAdmin): string | null {
  if (!provider.enabled) return null;
  if (!provider.configured) {
    return provider.missing.length
      ? `Switched on, but ${provider.missing.join(" and ")} ${
          provider.missing.length === 1 ? "is" : "are"
        } not saved, so nothing can connect through it.`
      : "Switched on, but no credentials are saved, so nothing can connect through it.";
  }
  if (!provider.last_test?.at) {
    return "Credentials are saved but have never been tested, so a rejected key would only surface when a user tries to connect.";
  }
  return null;
}

function CredentialInput({
  field,
  value,
  onChange,
}: {
  field: ProviderCredentialField;
  value: string;
  onChange: (next: string) => void;
}) {
  const id = `${field.key}-input`;
  const hint = field.present
    ? field.secret
      ? `Saved (${field.hint ?? "hidden"}). Leave blank to keep it.`
      : undefined
    : field.help;
  return (
    <Field label={field.label} htmlFor={id} hint={hint} error={field.required && !field.present ? "Required" : null}>
      {field.multiline ? (
        <Textarea
          id={id}
          rows={4}
          spellCheck={false}
          autoComplete="off"
          value={value}
          placeholder={field.placeholder ?? (field.present ? "Leave blank to keep the saved value" : "")}
          onChange={(event) => onChange(event.target.value)}
        />
      ) : (
        <Input
          id={id}
          type={field.secret ? "password" : "text"}
          autoComplete="off"
          spellCheck={false}
          value={value}
          placeholder={field.placeholder ?? (field.present ? "Leave blank to keep the saved value" : "")}
          onChange={(event) => onChange(event.target.value)}
        />
      )}
    </Field>
  );
}

function ProviderCard({
  provider,
  primary,
  onChanged,
}: {
  provider: ProviderAdmin;
  primary: boolean;
  onChanged: () => void;
}) {
  const [enabled, setEnabled] = useState(provider.enabled);
  const [priority, setPriority] = useState(String(provider.priority));
  const [environment, setEnvironment] = useState(provider.environment);
  const [values, setValues] = useState<Record<string, string>>({});
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const save = useMutation({
    mutationFn: (credentials: Record<string, string>) =>
      api.providerAdmin.update(provider.name, {
        enabled,
        priority: Number(priority),
        environment,
        credentials,
      }),
    onSuccess: () => {
      setValues({});
      setMessage("Saved.");
      setError(null);
      onChanged();
    },
    onError: (err) => setError(err instanceof Error ? err.message : "Could not save."),
  });

  const test = useMutation({
    mutationFn: () => api.providerAdmin.test(provider.name),
    onSuccess: (result) => {
      setMessage(result.message);
      onChanged();
    },
    onError: (err) => setError(err instanceof Error ? err.message : "The test failed."),
  });

  const submit = () => {
    const credentials: Record<string, string> = {};
    Object.entries(values).forEach(([key, value]) => {
      if (value !== "") credentials[key] = value;
    });
    setMessage(null);
    save.mutate(credentials);
  };

  return (
    <Card>
      <div className="list-row" style={{ alignItems: "center", gap: "0.75rem" }}>
        <div style={{ flex: 1 }}>
          <div style={{ display: "flex", gap: "0.5rem", alignItems: "center", flexWrap: "wrap" }}>
            <h2 style={{ fontSize: "1.05rem", margin: 0 }}>{provider.label}</h2>
            {primary ? <Badge tone="info">Primary</Badge> : null}
            {statusBadge(provider)}
            <Badge tone="neutral">{provider.environment}</Badge>
          </div>
          <p className="tiny muted" style={{ margin: "0.25rem 0 0" }}>
            {provider.source === "environment"
              ? "Credentials come from this server's environment variables."
              : provider.source === "database"
                ? "Credentials are stored encrypted in this server's database."
                : "No credentials have been provided yet."}
          </p>
        </div>
        <Button
          size="sm"
          variant="ghost"
          loading={test.isPending}
          onClick={() => {
            setMessage(null);
            setError(null);
            test.mutate();
          }}
        >
          Test connection
        </Button>
      </div>

      {provider.problem ? (
        <p className="tiny" style={{ color: "var(--danger)" }}>
          {provider.problem} Re-enter the credentials below.
        </p>
      ) : null}

      {/* A real form, so Enter in a credential field saves. Without it the only way
          to submit was the button, and typed values silently went nowhere. */}
      <form
        className="page-stack"
        style={{ gap: "0.9rem", marginTop: "0.9rem" }}
        onSubmit={(event) => {
          event.preventDefault();
          submit();
        }}
      >
        <div style={{ display: "grid", gap: "0.9rem", gridTemplateColumns: "1fr 1fr" }}>
          <Field label="Environment" htmlFor={`${provider.name}-environment`}>
            <Select
              id={`${provider.name}-environment`}
              value={environment}
              onChange={(event) => setEnvironment(event.target.value)}
            >
              {provider.environments.map((option) => (
                <option key={option} value={option}>
                  {option}
                </option>
              ))}
            </Select>
          </Field>
          <Field
            label="Priority"
            htmlFor={`${provider.name}-priority`}
            hint="Lower is tried first. Teller is 10 and Plaid 20."
          >
            <Input
              id={`${provider.name}-priority`}
              type="number"
              min={0}
              max={1000}
              value={priority}
              onChange={(event) => setPriority(event.target.value)}
            />
          </Field>
        </div>

        <label className="checkbox-row">
          <input
            type="checkbox"
            checked={enabled}
            onChange={(event) => setEnabled(event.target.checked)}
          />
          <span>
            Enabled for automatic selection.
            <span className="tiny" style={{ display: "block" }}>
              Disabling stops new connections through this provider. Existing connections keep
              syncing.
            </span>
          </span>
        </label>

        {provider.fields.map((field) => (
          <div key={field.key}>
            <CredentialInput
              field={field}
              value={values[field.key] ?? ""}
              onChange={(next) => setValues((prev) => ({ ...prev, [field.key]: next }))}
            />
            {field.present ? (
              <Button
                type="button"
                size="sm"
                variant="ghost"
                onClick={() => {
                  setMessage(null);
                  save.mutate({ [field.key]: "" });
                }}
              >
                Remove saved {field.label.toLowerCase()}
              </Button>
            ) : null}
          </div>
        ))}

        {error ? <p className="form-error">{error}</p> : null}
        {message ? <p className="tiny">{message}</p> : null}

        {provider.last_test ? (
          <div className="tiny muted">
            Last test {formatDate(provider.last_test.at ?? "", { dateStyle: "medium", timeStyle: "short" })}
            : {provider.last_test.ok ? "passed" : "failed"}
            {provider.last_test.message ? ` — ${provider.last_test.message}` : ""}
          </div>
        ) : null}

        <div>
          <Button type="submit" loading={save.isPending}>
            Save {provider.label} configuration
          </Button>
        </div>
      </form>
    </Card>
  );
}

function CoveragePanel() {
  const [names, setNames] = useState("USAA, Cash App");
  const [report, setReport] = useState<CoverageReport | null>(null);
  const [error, setError] = useState<string | null>(null);

  const run = useMutation({
    mutationFn: () =>
      api.providerAdmin.coverage(
        names
          .split(",")
          .map((part) => part.trim())
          .filter(Boolean)
      ),
    onSuccess: (result) => {
      setReport(result);
      setError(null);
    },
    onError: (err) =>
      setError(err instanceof Error ? err.message : "Could not check coverage."),
  });

  return (
    <Card>
      <h2 style={{ fontSize: "1.05rem", marginBottom: "0.25rem" }}>Institution coverage</h2>
      <p className="tiny muted" style={{ marginBottom: "0.9rem" }}>
        Ask every provider what it can do for specific institutions. A provider listing an
        institution does not mean it can supply transaction history — this shows the
        difference.
      </p>
      <div className="list-row" style={{ alignItems: "flex-end", gap: "0.75rem" }}>
        <div style={{ flex: 1 }}>
          <Field label="Institution names" htmlFor="coverage-names" hint="Comma separated.">
            <Input
              id="coverage-names"
              value={names}
              onChange={(event) => setNames(event.target.value)}
            />
          </Field>
        </div>
        <Button
          variant="secondary"
          loading={run.isPending}
          onClick={() => run.mutate()}
        >
          Check coverage
        </Button>
      </div>
      {error ? <p className="form-error">{error}</p> : null}
      {report ? (
        <div className="page-stack" style={{ gap: "1rem", marginTop: "1rem" }}>
          {report.institutions.map((row) => (
            <div key={row.query}>
              <strong>{row.query}</strong>
              <div className="page-stack" style={{ gap: "0.4rem", marginTop: "0.4rem" }}>
                {row.providers.map((provider) => (
                  <div key={provider.provider} className="list-row" style={{ gap: "0.6rem" }}>
                    <div style={{ width: 90 }}>
                      <span className="tiny mono">{provider.label}</span>
                    </div>
                    <div style={{ flex: 1 }} className="tiny">
                      {provider.match ? (
                        <>
                          {provider.match.name} ({provider.match.institution_id})
                          <span className="muted">
                            {" "}
                            · transactions {provider.match.transactions ? "yes" : "no"} · balances{" "}
                            {provider.match.balances ? "yes" : "no"}
                          </span>
                        </>
                      ) : (
                        <span className="muted">{provider.reason ?? "not listed"}</span>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      ) : null}
    </Card>
  );
}

export function ProvidersPage() {
  const queryClient = useQueryClient();
  const settingsQuery = useQuery({
    queryKey: ["server-settings"],
    queryFn: api.server.settings,
  });
  const isAdmin = settingsQuery.data?.settings.is_admin === true;

  const overviewQuery = useQuery({
    queryKey: ["provider-overview"],
    queryFn: api.providerAdmin.overview,
    enabled: isAdmin,
  });

  const selection = useMutation({
    mutationFn: (autoSelect: boolean) => api.providerAdmin.setSelection(autoSelect),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["provider-overview"] }),
  });

  if (settingsQuery.isLoading) return <LoadingBlock label="Checking permissions" />;
  if (!isAdmin) {
    return (
      <div className="page-stack">
        <PageHeader eyebrow="This server" title="Financial providers" />
        <Card>
          <p className="tiny" style={{ margin: 0 }}>
            Only the server administrator can view or change financial provider settings.
            Connecting your own institution from the Connections page works without this.
          </p>
        </Card>
      </div>
    );
  }
  if (overviewQuery.isLoading) return <LoadingBlock label="Reading provider configuration" />;
  if (overviewQuery.error || !overviewQuery.data) {
    return (
      <ErrorBanner
        message={
          overviewQuery.error instanceof Error
            ? overviewQuery.error.message
            : "Could not load provider configuration."
        }
        onRetry={() => void overviewQuery.refetch()}
      />
    );
  }

  const overview: ProviderOverview = overviewQuery.data;
  const blockers = overview.providers
    .map((provider) => ({ provider, message: connectionBlocker(provider) }))
    .filter((row): row is { provider: ProviderAdmin; message: string } => row.message !== null);
  const primary = overview.providers.find((p) => p.usable)?.name ?? null;
  const refresh = () => {
    void queryClient.invalidateQueries({ queryKey: ["provider-overview"] });
    void queryClient.invalidateQueries({ queryKey: ["institution-catalog"] });
  };

  return (
    <div className="page-stack">
      <PageHeader
        eyebrow="Administration"
        title="Financial providers"
        description="Configure the aggregators this server uses to connect institutions. Users never see this screen: they only search for their institution and approve access."
      />

      {blockers.length ? (
        <Card>
          <h2 style={{ fontSize: "1.05rem", margin: 0 }}>Not ready to connect anyone yet</h2>
          <p className="tiny muted" style={{ margin: "0.25rem 0 0.6rem" }}>
            These providers are switched on but cannot serve a connection. Users are told their
            institution is unavailable, with no sign that the cause is server-side.
          </p>
          <ul className="page-stack" style={{ gap: "0.35rem", margin: 0, paddingLeft: "1.1rem" }}>
            {blockers.map(({ provider, message }) => (
              <li key={provider.name} className="small">
                <strong>{provider.label}</strong> — {message}
              </li>
            ))}
          </ul>
        </Card>
      ) : null}

      <Card>
        <div className="list-row" style={{ alignItems: "center", gap: "0.75rem" }}>
          <div style={{ flex: 1 }}>
            <h2 style={{ fontSize: "1.05rem", margin: 0 }}>Automatic provider selection</h2>
            <p className="tiny muted" style={{ margin: "0.25rem 0 0" }}>
              When on, each institution is served by the highest-priority provider that
              supports it. When off, only the first ready provider is used and anything it
              cannot serve is reported as unavailable.
            </p>
          </div>
          <label className="checkbox-row">
            <input
              type="checkbox"
              checked={overview.auto_select}
              disabled={selection.isPending}
              onChange={(event) => selection.mutate(event.target.checked)}
            />
            <span>Enabled</span>
          </label>
        </div>
        {!overview.any_usable ? (
          <p className="tiny" style={{ color: "var(--danger)", marginBottom: 0 }}>
            No provider is ready yet, so nobody can connect an institution. Add credentials
            below, or set them with environment variables.
          </p>
        ) : null}
      </Card>

      {/* Keyed by name only: a refetch (after a test, or any refresh) used to remount
          the card, which discarded credentials the owner had just typed. */}
      {overview.providers.map((provider) => (
        <ProviderCard
          key={provider.name}
          provider={provider}
          primary={provider.name === primary}
          onChanged={refresh}
        />
      ))}

      <CoveragePanel />

      <Card>
        <h2 style={{ fontSize: "1.05rem", marginBottom: "0.5rem" }}>How this behaves</h2>
        <ul className="tiny" style={{ margin: 0, paddingLeft: "1.1rem", lineHeight: 1.7 }}>
          <li>Credentials are encrypted with a key held outside the database.</li>
          <li>
            Changing a saved credential clears the previous test result, because it only
            proved the old value.
          </li>
          <li>
            Existing connections keep syncing through whichever provider created them.
            Switching providers needs a reauthorisation, not a silent migration.
          </li>
          <li>
            {overview.sandbox_available
              ? "The simulated institution is enabled, so the whole flow can be exercised without credentials."
              : "The simulated institution is disabled on this server."}
          </li>
        </ul>
      </Card>
    </div>
  );
}
