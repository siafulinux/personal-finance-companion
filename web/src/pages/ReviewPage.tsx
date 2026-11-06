import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../lib/api";
import { formatDate, formatMoney, frequencyLabel } from "../lib/format";
import {
  Badge,
  Button,
  Card,
  EmptyState,
  ErrorBanner,
  LoadingBlock,
  PageHeader,
} from "../components/ui";

const SOURCE_LABEL: Record<string, string> = {
  rule: "Merchant rule",
  history: "Your history",
  provider: "From your bank",
};

export function ReviewPage() {
  const queryClient = useQueryClient();
  const [error, setError] = useState<string | null>(null);

  const suggestionsQuery = useQuery({
    queryKey: ["suggestions"],
    queryFn: () => api.review.suggestions(),
  });
  const recurringQuery = useQuery({
    queryKey: ["recurring"],
    queryFn: () => api.review.recurring(),
  });

  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: ["suggestions"] });
    queryClient.invalidateQueries({ queryKey: ["recurring"] });
    queryClient.invalidateQueries({ queryKey: ["transactions"] });
    queryClient.invalidateQueries({ queryKey: ["dashboard"] });
  };

  const accept = useMutation({
    mutationFn: (id: string) => api.review.accept(id),
    onSuccess: invalidate,
    onError: (err) => setError(err instanceof Error ? err.message : "Could not accept."),
  });
  const reject = useMutation({
    mutationFn: (id: string) => api.review.reject(id),
    onSuccess: invalidate,
    onError: (err) => setError(err instanceof Error ? err.message : "Could not dismiss."),
  });
  const detect = useMutation({
    mutationFn: () => api.review.detectRecurring(),
    onSuccess: invalidate,
    onError: (err) => setError(err instanceof Error ? err.message : "Detection failed."),
  });
  const confirmSeries = useMutation({
    mutationFn: (id: string) => api.review.confirmRecurring(id),
    onSuccess: invalidate,
  });
  const dismissSeries = useMutation({
    mutationFn: (id: string) => api.review.dismissRecurring(id),
    onSuccess: invalidate,
  });

  if (suggestionsQuery.isLoading || recurringQuery.isLoading) {
    return <LoadingBlock label="Loading suggestions" />;
  }

  const suggestions = suggestionsQuery.data?.items ?? [];
  const recurring = recurringQuery.data?.items ?? [];
  const subscriptions = recurring.filter((item) => item.is_subscription);

  return (
    <div className="page-stack">
      <PageHeader
        eyebrow="Review queue"
        title="Suggestions and subscriptions"
        description="Automation proposes; you decide. Accepting a category marks it as your own choice, so nothing will overwrite it later."
      />

      {error ? <ErrorBanner message={error} onRetry={() => setError(null)} /> : null}

      <Card>
        <div className="list-row" style={{ alignItems: "center" }}>
          <div style={{ flex: 1 }}>
            <h2 style={{ fontSize: "1.05rem" }}>Category suggestions</h2>
            <p className="tiny muted">
              {suggestions.length} pending. Each carries the reason it was proposed.
            </p>
          </div>
        </div>

        {suggestions.length === 0 ? (
          <EmptyState
            title="Nothing to review"
            description="Suggestions appear after transactions are imported or created."
          />
        ) : (
          <div className="page-stack" style={{ gap: "0.5rem", marginTop: "0.75rem" }}>
            {suggestions.map((item) => (
              <div
                key={item.id}
                className="list-row"
                style={{ alignItems: "center", gap: "0.75rem" }}
              >
                <div style={{ flex: 1 }}>
                  <strong>{item.transaction?.merchant || item.transaction?.description}</strong>
                  <div className="tiny muted">
                    {formatMoney(item.transaction?.amount ?? "0")} ·{" "}
                    {formatDate(item.transaction?.txn_date)} · suggesting{" "}
                    <strong>{item.category_name}</strong>
                  </div>
                  <div className="tiny muted">
                    {item.reason} · {SOURCE_LABEL[item.source] ?? item.source} · confidence{" "}
                    {Number(item.confidence).toFixed(2)}
                  </div>
                </div>
                <Button
                  size="sm"
                  loading={accept.isPending && accept.variables === item.id}
                  onClick={() => accept.mutate(item.id)}
                >
                  Accept
                </Button>
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={() => reject.mutate(item.id)}
                >
                  Dismiss
                </Button>
              </div>
            ))}
          </div>
        )}
      </Card>

      <Card>
        <div className="list-row" style={{ alignItems: "center" }}>
          <div style={{ flex: 1 }}>
            <h2 style={{ fontSize: "1.05rem" }}>Recurring charges</h2>
            <p className="tiny muted">
              {subscriptions.length} look like subscriptions, worth{" "}
              {formatMoney(recurringQuery.data?.subscription_monthly_total ?? "0")} a cycle.
              {" "}Detected from your own history over the last 180 days.
            </p>
          </div>
          <Button
            size="sm"
            variant="ghost"
            loading={detect.isPending}
            onClick={() => detect.mutate()}
          >
            Scan again
          </Button>
        </div>

        {recurring.length === 0 ? (
          <EmptyState
            title="No recurring charges found"
            description="At least three charges on a stable cadence are needed before a pattern is claimed."
            action={
              <Button size="sm" loading={detect.isPending} onClick={() => detect.mutate()}>
                Scan my history
              </Button>
            }
          />
        ) : (
          <div className="page-stack" style={{ gap: "0.5rem", marginTop: "0.75rem" }}>
            {recurring.map((item) => (
              <div
                key={item.id}
                className="list-row"
                style={{ alignItems: "center", gap: "0.75rem" }}
              >
                <div style={{ flex: 1 }}>
                  <div style={{ display: "flex", gap: "0.5rem", alignItems: "center" }}>
                    <strong>{item.display_name}</strong>
                    {item.is_subscription ? <Badge tone="info">Subscription</Badge> : null}
                    {item.status === "confirmed" ? <Badge tone="positive">Confirmed</Badge> : null}
                  </div>
                  <div className="tiny muted">
                    {formatMoney(item.average_amount)} · {frequencyLabel(item.frequency)} ·{" "}
                    {item.occurrences} charges · next expected{" "}
                    {formatDate(item.next_expected_date)}
                  </div>
                  <div className="tiny muted">
                    Interval {item.interval_days} days · confidence{" "}
                    {Number(item.confidence).toFixed(2)} · heuristic, not a bill
                  </div>
                </div>
                {item.status !== "confirmed" ? (
                  <Button
                    size="sm"
                    loading={confirmSeries.isPending && confirmSeries.variables === item.id}
                    onClick={() => confirmSeries.mutate(item.id)}
                  >
                    Keep watching
                  </Button>
                ) : null}
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={() => dismissSeries.mutate(item.id)}
                >
                  Not a pattern
                </Button>
              </div>
            ))}
          </div>
        )}
      </Card>
    </div>
  );
}
