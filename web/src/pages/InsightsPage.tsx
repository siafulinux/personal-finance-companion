import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../lib/api";
import { formatDate, formatMoney } from "../lib/format";
import {
  Badge,
  Card,
  EmptyState,
  ErrorBanner,
  LoadingBlock,
  PageHeader,
  Select,
} from "../components/ui";

const SEVERITY_TONE = {
  high: "danger",
  medium: "warning",
  low: "neutral",
} as const;

export function InsightsPage() {
  const queryClient = useQueryClient();
  const [error, setError] = useState<string | null>(null);

  const insightsQuery = useQuery({
    queryKey: ["personal-insights"],
    queryFn: api.personal.insights,
  });

  const updatePrefs = useMutation({
    mutationFn: api.personal.updatePreferences,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["personal-insights"] }),
    onError: (err) => setError(err instanceof Error ? err.message : "Could not save."),
  });

  if (insightsQuery.isLoading) return <LoadingBlock label="Reading your history" />;

  const data = insightsQuery.data;
  if (!data) return <ErrorBanner message="Could not load insights." />;

  return (
    <div className="page-stack">
      <PageHeader
        eyebrow="Spending behaviour"
        title="Insights"
        description="Observations built from your own transactions. Every statement shows the numbers behind it, and nothing is claimed until there are at least three months and five transactions of history."
      />

      {error ? <ErrorBanner message={error} onRetry={() => setError(null)} /> : null}

      <Card>
        <div className="list-row" style={{ alignItems: "center", gap: "0.75rem" }}>
          <div style={{ flex: 1 }}>
            <h2 style={{ fontSize: "1.05rem" }}>Settings</h2>
            <p className="tiny muted">
              Sensitivity widens or narrows what counts as worth telling you.
            </p>
          </div>
          <label className="tiny" style={{ display: "flex", gap: "0.4rem", alignItems: "center" }}>
            <input
              type="checkbox"
              checked={data.enabled}
              onChange={(event) =>
                updatePrefs.mutate({ personalized_insights_enabled: event.target.checked })
              }
            />
            Personalised insights
          </label>
          <Select
            value={data.sensitivity}
            onChange={(event) =>
              updatePrefs.mutate({ insight_sensitivity: event.target.value })
            }
            style={{ width: "9rem" }}
            aria-label="Insight sensitivity"
          >
            <option value="low">Low</option>
            <option value="normal">Normal</option>
            <option value="high">High</option>
          </Select>
        </div>
        <p className="tiny muted" style={{ marginTop: "0.5rem" }}>
          Requires {data.minimum_history.months} months and {data.minimum_history.transactions}{" "}
          transactions before any merchant or category judgement is made.
        </p>
      </Card>

      <Card>
        <h2 style={{ fontSize: "1.05rem", marginBottom: "0.75rem" }}>What stands out</h2>
        {!data.enabled ? (
          <EmptyState
            title="Insights are off"
            description="Turn them back on above to see observations about your spending."
          />
        ) : data.insights.length === 0 ? (
          <EmptyState
            title="Nothing needs attention"
            description="Either your spending is inside plan, or there is not enough history yet to say anything useful."
          />
        ) : (
          <div className="page-stack" style={{ gap: "0.75rem" }}>
            {data.insights.map((insight, index) => (
              <div key={`${insight.type}-${index}`} className="page-stack" style={{ gap: "0.25rem" }}>
                <div style={{ display: "flex", gap: "0.5rem", alignItems: "center" }}>
                  <Badge tone={SEVERITY_TONE[insight.severity]}>{insight.severity}</Badge>
                  <strong>{insight.title}</strong>
                </div>
                <p className="tiny">{insight.message}</p>
                <div className="tiny muted mono">
                  {Object.entries(insight.evidence)
                    .map(([key, value]) => `${key.replace(/_/g, " ")}: ${value}`)
                    .join(" · ")}
                </div>
              </div>
            ))}
          </div>
        )}
      </Card>

      <Card>
        <h2 style={{ fontSize: "1.05rem", marginBottom: "0.75rem" }}>Unusual transactions</h2>
        {data.unusual_transactions.length === 0 ? (
          <div className="tiny muted">
            No transaction is materially above what is usual for its merchant.
          </div>
        ) : (
          <div className="page-stack" style={{ gap: "0.5rem" }}>
            {data.unusual_transactions.map((row) => (
              <div key={row.transaction_id} className="list-row" style={{ alignItems: "center" }}>
                <div style={{ flex: 1 }}>
                  <strong>{row.merchant || row.description}</strong>
                  <div className="tiny muted">
                    {formatMoney(row.amount)} on {formatDate(row.txn_date)} · usually{" "}
                    {formatMoney(row.typical_amount)} ({row.times_typical}×)
                  </div>
                </div>
                <Badge tone="warning">Unusual</Badge>
              </div>
            ))}
          </div>
        )}
      </Card>

      <p className="tiny muted">
        These are observations from the deterministic engine, not advice. They never move money
        or change a category.
      </p>
    </div>
  );
}
