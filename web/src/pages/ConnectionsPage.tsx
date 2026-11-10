import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../lib/api";
import {
  ConnectCancelled,
  openPlaidLink,
  openTellerConnect,
  tellerFinishPayload,
} from "../lib/providerConnect";
import { formatDate } from "../lib/format";
import type {
  ConnectFlow,
  InstitutionEntry,
  ProviderLink,
  SyncRunSummary,
} from "../lib/types";
import {
  Badge,
  Button,
  Card,
  ConfirmDialog,
  EmptyState,
  ErrorBanner,
  Field,
  Input,
  LoadingBlock,
  Modal,
  PageHeader,
  Warnings,
} from "../components/ui";

function statusTone(status: ProviderLink["status"]) {
  if (status === "active") return "positive" as const;
  if (status === "reauth_required") return "danger" as const;
  if (status === "error") return "warning" as const;
  return "neutral" as const;
}

function statusLabel(link: ProviderLink) {
  if (link.status === "active") return "Connected";
  if (link.status === "error") return "Needs retry";
  if (link.status === "reauth_required") return "Reconnect needed";
  return "Disconnected";
}

function asString(value: unknown): string {
  return typeof value === "string" ? value : "";
}

function asStringList(value: unknown): string[] {
  return Array.isArray(value)
    ? value.filter((item): item is string => typeof item === "string")
    : [];
}

function RunRow({ run }: { run: SyncRunSummary }) {
  const tone =
    run.status === "success" ? "positive" : run.status === "partial" ? "warning" : "danger";
  return (
    <div className="list-row" style={{ alignItems: "flex-start", gap: "0.75rem" }}>
      <Badge tone={tone}>{run.status}</Badge>
      <div style={{ flex: 1 }}>
        <div className="mono tiny">
          {formatDate(run.started_at, { dateStyle: "medium", timeStyle: "short" })}
        </div>
        <div className="tiny muted">
          +{run.added} added · ~{run.modified} updated · −{run.removed} removed
          {run.skipped_duplicates ? ` · ${run.skipped_duplicates} duplicates skipped` : ""}
          {run.suggestions_created ? ` · ${run.suggestions_created} suggestions` : ""}
        </div>
        {run.error_message ? (
          <div className="tiny" style={{ color: "var(--danger)" }}>
            {run.error_code}: {run.error_message}
          </div>
        ) : null}
      </div>
    </div>
  );
}

export function ConnectionsPage() {
  const queryClient = useQueryClient();
  const [search, setSearch] = useState("");
  const [query, setQuery] = useState("");

  // Typing should not fire a request per keystroke; the directory is server-side.
  useEffect(() => {
    const timer = window.setTimeout(() => setQuery(search.trim()), 250);
    return () => window.clearTimeout(timer);
  }, [search]);

  const catalogQuery = useQuery({
    queryKey: ["institution-catalog", query],
    queryFn: () => api.connectivity.catalog(query),
  });
  const linksQuery = useQuery({ queryKey: ["links"], queryFn: api.connectivity.links });
  const runsQuery = useQuery({
    queryKey: ["sync-runs"],
    queryFn: () => api.connectivity.syncRuns(10),
  });

  const [pendingUnlink, setPendingUnlink] = useState<ProviderLink | null>(null);
  const [deleteData, setDeleteData] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const [selected, setSelected] = useState<InstitutionEntry | null>(null);
  const [consent, setConsent] = useState(false);
  const [connecting, setConnecting] = useState(false);
  const [connectError, setConnectError] = useState<string | null>(null);

  const refresh = () => {
    queryClient.invalidateQueries({ queryKey: ["links"] });
    queryClient.invalidateQueries({ queryKey: ["sync-runs"] });
    queryClient.invalidateQueries({ queryKey: ["transactions"] });
    queryClient.invalidateQueries({ queryKey: ["accounts"] });
    queryClient.invalidateQueries({ queryKey: ["review"] });
    queryClient.invalidateQueries({ queryKey: ["suggestions"] });
    queryClient.invalidateQueries({ queryKey: ["dashboard"] });
  };

  const closeConnect = () => {
    setSelected(null);
    setConsent(false);
    setConnectError(null);
  };

  const connect = async (entry: InstitutionEntry) => {
    setConnecting(true);
    setConnectError(null);
    try {
      const started: ConnectFlow = await api.connectivity.start({
        institution_name: entry.name,
        institution_key: entry.key,
      });

      type FinishExtra = {
        public_token: string;
        nonce?: string;
        user_id?: string | null;
        enrollment_id?: string | null;
        signatures?: string[];
      };

      const complete = async (extra: FinishExtra) => {
        const result = await api.connectivity.finish({
          institution_name: entry.name,
          institution_key: entry.key,
          consent: true,
          ...extra,
        });
        setNotice(
          `${result.link.institution_name} connected. ${result.sync.added} transactions imported` +
            (result.sync.skipped_duplicates
              ? `, ${result.sync.skipped_duplicates} duplicates skipped.`
              : ".")
        );
        refresh();
        closeConnect();
      };

      if (started.mode === "direct") {
        // A locally simulated institution approves immediately.
        await complete({ public_token: asString(started.flow.link_token) });
      } else if (started.mode === "teller_connect") {
        const nonce = asString(started.flow.nonce);
        const enrollment = await openTellerConnect({
          applicationId: asString(started.flow.application_id),
          environment: asString(started.flow.environment) || "sandbox",
          products: asStringList(started.flow.products),
          nonce,
          institution: asString(started.flow.institution) || null,
        });
        await complete(tellerFinishPayload(enrollment, nonce));
      } else if (started.mode === "plaid_link") {
        const publicToken = await openPlaidLink(asString(started.flow.link_token));
        await complete({ public_token: publicToken });
      } else {
        throw new Error("This server returned a connection flow this app does not recognise.");
      }
    } catch (err) {
      if (err instanceof ConnectCancelled) {
        setConnectError(null);
      } else {
        setConnectError(
          err instanceof Error ? err.message : "Could not connect this institution."
        );
      }
    } finally {
      setConnecting(false);
    }
  };

  const sync = useMutation({
    mutationFn: ({ id, full }: { id: string; full: boolean }) =>
      api.connectivity.sync(id, full),
    onSuccess: (result) => {
      const run = result.sync;
      setError(result.error ?? null);
      setNotice(
        `Sync ${run.status}: +${run.added} new, ~${run.modified} updated, ` +
          `${run.skipped_duplicates} duplicates skipped.`
      );
      refresh();
    },
    onError: (err) => setError(err instanceof Error ? err.message : "Sync failed."),
  });

  const unlink = useMutation({
    mutationFn: ({ id, del }: { id: string; del: boolean }) =>
      api.connectivity.unlink(id, del),
    onSuccess: (result) => {
      setPendingUnlink(null);
      setNotice(
        `Disconnected. ${result.deleted_transactions} transactions and ` +
          `${result.deleted_accounts} accounts removed; ${result.kept_accounts} kept.`
      );
      refresh();
    },
    onError: (err) => setError(err instanceof Error ? err.message : "Could not disconnect."),
  });

  if (linksQuery.isLoading) {
    return <LoadingBlock label="Loading connections" />;
  }

  const links = linksQuery.data?.links ?? [];
  const catalog = catalogQuery.data;
  const institutions = catalog?.institutions ?? [];

  return (
    <div className="page-stack">
      <PageHeader
        eyebrow="Connected data"
        title="Institutions"
        description="Connect your bank or payment app to bring its accounts and transactions into your ledger. They become ordinary ledger rows: the same balances, bills and Safe-to-Spend apply."
      />

      {error ? <ErrorBanner message={error} onRetry={() => setError(null)} /> : null}
      {notice ? (
        <Card>
          <div className="tiny">{notice}</div>
        </Card>
      ) : null}

      <Card>
        <h2 style={{ fontSize: "1.05rem", marginBottom: "0.25rem" }}>Connect an institution</h2>
        <p className="tiny muted" style={{ marginBottom: "0.9rem" }}>
          Search for your bank, credit union or payment app. Your credentials are entered
          directly with the institution's secure authorisation screen — this server never
          sees your bank password.
        </p>

        <Field label="Search institutions" htmlFor="institution-search">
          <Input
            id="institution-search"
            type="search"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder="USAA, Chase, Cash App…"
            autoComplete="off"
          />
        </Field>

        {catalogQuery.isLoading ? (
          <div className="tiny muted" style={{ marginTop: "0.9rem" }}>
            Searching…
          </div>
        ) : catalogQuery.error ? (
          <div className="tiny" style={{ marginTop: "0.9rem", color: "var(--danger)" }}>
            {catalogQuery.error instanceof Error
              ? catalogQuery.error.message
              : "Could not load the institution list."}
          </div>
        ) : institutions.length === 0 ? (
          <div className="tiny muted" style={{ marginTop: "0.9rem" }}>
            {catalog?.configured
              ? "No institution matches that search. You can still add the account manually or import a statement."
              : "Financial connections are not set up on this server yet. Ask the administrator to finish the provider configuration — manual entry and statement import still work."}
          </div>
        ) : (
          <div className="page-stack" style={{ gap: "0.6rem", marginTop: "0.9rem" }}>
            {institutions.map((entry) => (
              <div
                key={entry.key}
                className="list-row"
                style={{ alignItems: "center", gap: "0.75rem" }}
              >
                <div style={{ flex: 1 }}>
                  <strong>{entry.name}</strong>
                  <div className="tiny muted">
                    {entry.available
                      ? entry.account_types.length
                        ? `Shares ${entry.account_types.join(", ").replaceAll("_", " ")}`
                        : "Ready to connect"
                      : entry.reason ?? "Currently unavailable"}
                  </div>
                </div>
                {entry.simulated ? <Badge tone="info">Demo</Badge> : null}
                <Button
                  size="sm"
                  disabled={!entry.available}
                  onClick={() => {
                    setNotice(null);
                    setConsent(false);
                    setConnectError(null);
                    setSelected(entry);
                  }}
                >
                  {entry.available ? "Connect" : "Unavailable"}
                </Button>
              </div>
            ))}
          </div>
        )}

        {catalog?.warnings?.length ? <Warnings items={catalog.warnings} /> : null}
      </Card>

      <Card>
        <h2 style={{ fontSize: "1.05rem", marginBottom: "0.75rem" }}>Connected institutions</h2>
        {links.length === 0 ? (
          <EmptyState
            title="Nothing connected yet"
            description="Connect an institution above to import its accounts and transactions, or keep adding them manually."
          />
        ) : (
          <div className="page-stack" style={{ gap: "1rem" }}>
            {links.map((link) => (
              <div key={link.id} className="page-stack" style={{ gap: "0.5rem" }}>
                <div className="list-row" style={{ alignItems: "center", gap: "0.75rem" }}>
                  <div style={{ flex: 1 }}>
                    <div style={{ display: "flex", gap: "0.5rem", alignItems: "center" }}>
                      <strong>{link.institution_name}</strong>
                      <Badge tone={statusTone(link.status)}>{statusLabel(link)}</Badge>
                    </div>
                    <div className="tiny muted">
                      {link.account_count} accounts · last synced{" "}
                      {link.last_synced_at
                        ? formatDate(link.last_synced_at, {
                            dateStyle: "medium",
                            timeStyle: "short",
                          })
                        : "never"}
                      {link.next_retry_at
                        ? ` · next retry ${formatDate(link.next_retry_at, {
                            dateStyle: "medium",
                            timeStyle: "short",
                          })}`
                        : ""}
                    </div>
                    {link.error_message ? (
                      <div className="tiny" style={{ color: "var(--danger)" }}>
                        {link.error_code}: {link.error_message}
                      </div>
                    ) : null}
                    <div className="tiny muted">
                      {link.accounts.map((account) => account.name).join(" · ")}
                    </div>
                  </div>
                  <Button
                    size="sm"
                    variant="ghost"
                    loading={sync.isPending && sync.variables?.id === link.id}
                    onClick={() => sync.mutate({ id: link.id, full: false })}
                  >
                    Sync now
                  </Button>
                  <Button
                    size="sm"
                    variant="ghost"
                    onClick={() => sync.mutate({ id: link.id, full: true })}
                  >
                    Full refresh
                  </Button>
                  <Button
                    size="sm"
                    variant="danger"
                    onClick={() => {
                      setDeleteData(false);
                      setPendingUnlink(link);
                    }}
                  >
                    Disconnect
                  </Button>
                </div>
                {link.status === "reauth_required" ? (
                  <p className="tiny" style={{ margin: 0 }}>
                    The institution needs you to sign in again before data can be refreshed.
                  </p>
                ) : null}
                {link.last_run ? <RunRow run={link.last_run} /> : null}
              </div>
            ))}
          </div>
        )}
      </Card>

      <Card>
        <h2 style={{ fontSize: "1.05rem", marginBottom: "0.75rem" }}>Recent sync history</h2>
        {(runsQuery.data?.runs ?? []).length === 0 ? (
          <div className="tiny muted">No sync has run yet.</div>
        ) : (
          <div className="page-stack" style={{ gap: "0.35rem" }}>
            {(runsQuery.data?.runs ?? []).map((run) => (
              <RunRow key={run.id} run={run} />
            ))}
          </div>
        )}
      </Card>

      <Modal
        open={selected !== null}
        title={selected ? `Connect ${selected.name}` : "Connect institution"}
        description="You will approve the request on the institution's own secure screen."
        onClose={closeConnect}
        footer={
          <>
            <Button variant="ghost" onClick={closeConnect} disabled={connecting}>
              Cancel
            </Button>
            <Button
              disabled={!consent || connecting}
              loading={connecting}
              onClick={() => selected && void connect(selected)}
            >
              {connecting ? "Connecting…" : "Authorise and connect"}
            </Button>
          </>
        }
      >
        <div className="page-stack" style={{ gap: "0.9rem" }}>
          <p className="tiny" style={{ margin: 0 }}>
            This server will retrieve the accounts you select and their transaction history
            from <strong>{selected?.name}</strong>, and keep them in sync until you disconnect.
            You can disconnect at any time and optionally delete the imported data.
          </p>
          {selected?.simulated ? (
            <p className="tiny muted" style={{ margin: 0 }}>
              This is a simulated institution for trying the flow. It holds no real accounts.
            </p>
          ) : null}
          <label className="checkbox-row">
            <input
              type="checkbox"
              checked={consent}
              onChange={(event) => setConsent(event.target.checked)}
            />
            <span>
              I authorise this server to access my account and transaction data at{" "}
              {selected?.name}.
            </span>
          </label>
          {connectError ? <ErrorBanner message={connectError} /> : null}
        </div>
      </Modal>

      <ConfirmDialog
        open={pendingUnlink !== null}
        title="Disconnect this institution?"
        destructive
        busy={unlink.isPending}
        confirmLabel={deleteData ? "Disconnect and delete data" : "Disconnect"}
        message={
          <div className="page-stack" style={{ gap: "0.75rem" }}>
            <p>
              Access will be revoked and the stored credential deleted. This does not stop the
              institution itself from existing — it only ends this connection.
            </p>
            <label style={{ display: "flex", gap: "0.5rem", alignItems: "flex-start" }}>
              <input
                type="checkbox"
                checked={deleteData}
                onChange={(event) => setDeleteData(event.target.checked)}
              />
              <span>
                Also delete the transactions and accounts this institution imported. Accounts
                with other history are archived instead of deleted.
              </span>
            </label>
          </div>
        }
        onCancel={() => setPendingUnlink(null)}
        onConfirm={() =>
          pendingUnlink && unlink.mutate({ id: pendingUnlink.id, del: deleteData })
        }
      />
    </div>
  );
}
