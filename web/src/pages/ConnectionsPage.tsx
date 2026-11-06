import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../lib/api";
import { formatDate } from "../lib/format";
import type { ProviderLink, SyncRunSummary } from "../lib/types";
import {
  Badge,
  Button,
  Card,
  ConfirmDialog,
  EmptyState,
  ErrorBanner,
  LoadingBlock,
  PageHeader,
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

function RunRow({ run }: { run: SyncRunSummary }) {
  const tone =
    run.status === "success" ? "positive" : run.status === "partial" ? "warning" : "danger";
  return (
    <div className="list-row" style={{ alignItems: "flex-start", gap: "0.75rem" }}>
      <Badge tone={tone}>{run.status}</Badge>
      <div style={{ flex: 1 }}>
        <div className="mono tiny">{formatDate(run.started_at, { dateStyle: "medium", timeStyle: "short" })}</div>
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
  const providersQuery = useQuery({
    queryKey: ["providers"],
    queryFn: api.connectivity.providers,
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

  const refresh = () => {
    queryClient.invalidateQueries({ queryKey: ["links"] });
    queryClient.invalidateQueries({ queryKey: ["sync-runs"] });
    queryClient.invalidateQueries({ queryKey: ["transactions"] });
    queryClient.invalidateQueries({ queryKey: ["accounts"] });
    queryClient.invalidateQueries({ queryKey: ["review"] });
    queryClient.invalidateQueries({ queryKey: ["suggestions"] });
  };

  const connect = useMutation({
    mutationFn: async (provider: string) => {
      const token = await api.connectivity.linkToken(provider);
      // The sandbox provider is a direct flow; a hosted provider would open its own
      // window here and hand back a public token.
      return api.connectivity.exchange({
        provider: token.provider,
        public_token: token.link_token,
        consent: true,
      });
    },
    onSuccess: (result) => {
      setError(null);
      setNotice(
        `${result.link.institution_name} connected. ${result.sync.added} transactions imported` +
          (result.sync.skipped_duplicates
            ? `, ${result.sync.skipped_duplicates} duplicates skipped.`
            : ".")
      );
      refresh();
    },
    onError: (err) => setError(err instanceof Error ? err.message : "Could not connect."),
  });

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

  if (providersQuery.isLoading || linksQuery.isLoading) {
    return <LoadingBlock label="Loading connections" />;
  }

  const providers = providersQuery.data?.providers ?? [];
  const links = linksQuery.data?.links ?? [];

  return (
    <div className="page-stack">
      <PageHeader
        eyebrow="Connected data"
        title="Institutions"
        description="Link an institution to bring its accounts and transactions into your ledger. Imported transactions are ordinary ledger rows: they feed the same balances, bills and Safe-to-Spend as manual entry."
      />

      {error ? <ErrorBanner message={error} onRetry={() => setError(null)} /> : null}
      {notice ? (
        <Card>
          <div className="tiny">{notice}</div>
        </Card>
      ) : null}

      <Card>
        <h2 style={{ fontSize: "1.05rem", marginBottom: "0.25rem" }}>Available providers</h2>
        <p className="tiny muted" style={{ marginBottom: "0.9rem" }}>
          The sandbox institution is simulated and needs no bank credentials. It exists so the
          whole pipeline can be exercised and reviewed safely.
        </p>
        <div className="page-stack" style={{ gap: "0.6rem" }}>
          {providers.map((provider) => (
            <div
              key={provider.name}
              className="list-row"
              style={{ alignItems: "center", gap: "0.75rem" }}
            >
              <div style={{ flex: 1 }}>
                <strong>{provider.display_name}</strong>
                <div className="tiny muted">{provider.note}</div>
              </div>
              {provider.simulated ? <Badge tone="info">Simulated</Badge> : null}
              <Button
                size="sm"
                disabled={!provider.usable}
                loading={connect.isPending && connect.variables === provider.name}
                onClick={() => {
                  setNotice(null);
                  connect.mutate(provider.name);
                }}
              >
                {provider.usable ? "Connect" : "Not configured"}
              </Button>
            </div>
          ))}
        </div>
      </Card>

      <Card>
        <h2 style={{ fontSize: "1.05rem", marginBottom: "0.75rem" }}>Connected institutions</h2>
        {links.length === 0 ? (
          <EmptyState
            title="Nothing connected yet"
            description="Connect a provider above to import accounts and transactions."
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
                      <Badge tone="neutral">{link.provider}</Badge>
                    </div>
                    <div className="tiny muted">
                      {link.account_count} accounts · last synced{" "}
                      {link.last_synced_at
                        ? formatDate(link.last_synced_at, {
                            dateStyle: "medium",
                            timeStyle: "short",
                          })
                        : "never"}
                      {link.next_retry_at ? ` · next retry ${formatDate(link.next_retry_at, { dateStyle: "medium", timeStyle: "short" })}` : ""}
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
