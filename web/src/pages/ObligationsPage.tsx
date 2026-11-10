import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { api } from "../lib/api";
import { formatDate, formatMoney, relativeDueLabel, todayISO } from "../lib/format";
import type { ObligationItem } from "../lib/types";
import {
  Badge,
  Card,
  EmptyState,
  ErrorBanner,
  LoadingBlock,
  PageHeader,
  SegmentedControl,
} from "../components/ui";

const KIND_LABEL: Record<ObligationItem["kind"], string> = {
  bill: "Bill",
  loan: "Loan repayment",
  credit_card: "Credit card",
};

export function ObligationsPage() {
  const [filter, setFilter] = useState<"all" | "overdue" | "week">("all");
  const today = todayISO();
  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ["obligations", 45],
    queryFn: () => api.obligations.list(45),
  });

  if (isLoading) return <LoadingBlock label="Adding up what is due" />;
  if (error || !data) {
    return (
      <ErrorBanner
        message={error instanceof Error ? error.message : "Could not load obligations."}
        onRetry={() => void refetch()}
      />
    );
  }

  const items = data.items.filter((item) => {
    if (filter === "overdue") return item.is_overdue;
    if (filter === "week") {
      if (!item.due_date) return false;
      const days = Math.round(
        (new Date(`${item.due_date}T00:00:00`).getTime() - new Date(`${today}T00:00:00`).getTime()) /
          86_400_000,
      );
      return days >= 0 && days <= 7;
    }
    return true;
  });

  return (
    <div className="page-stack">
      <PageHeader
        eyebrow="Obligations"
        title="Everything that is already promised"
        description="Bills, loan and advance repayments and the credit card minimums you entered, in one ordered list. The same figures feed Safe-to-Spend, so nothing here is counted twice."
        actions={
          <SegmentedControl
            value={filter}
            onChange={setFilter}
            ariaLabel="Filter obligations"
            options={[
              { value: "all", label: "All" },
              { value: "overdue", label: "Overdue" },
              { value: "week", label: "Next 7 days" },
            ]}
          />
        }
      />

      <div className="grid grid--three">
        <Card>
          <div className="stat">
            <span className="stat__label">Due in {data.horizon_end ? "the horizon" : "45 days"}</span>
            <span className="stat__value">{formatMoney(data.totals.due_in_horizon)}</span>
            <span className="stat__hint">{data.counts.total} item(s) through {formatDate(data.horizon_end)}</span>
          </div>
        </Card>
        <Card>
          <div className="stat">
            <span className="stat__label">Before payday</span>
            <span className="stat__value">{formatMoney(data.totals.due_before_payday)}</span>
            <span className="stat__hint">
              {data.next_payday ? `Payday ${formatDate(data.next_payday)}` : "No payday recorded"}
            </span>
          </div>
        </Card>
        <Card>
          <div className="stat">
            <span className="stat__label">Overdue</span>
            <span className={`stat__value ${Number(data.totals.overdue) > 0 ? "amount--negative" : ""}`}>
              {formatMoney(data.totals.overdue)}
            </span>
            <span className="stat__hint">{data.counts.overdue} item(s) past their date</span>
          </div>
        </Card>
      </div>

      {data.data_freshness.warning ? (
        <Card>
          <Badge tone="warning">Data may be stale</Badge>
          <p className="small muted" style={{ marginTop: "0.4rem" }}>
            {data.data_freshness.warning} Last transaction{" "}
            {data.data_freshness.last_transaction_date
              ? formatDate(data.data_freshness.last_transaction_date)
              : "never recorded"}
            .
          </p>
        </Card>
      ) : null}

      <Card>
        {items.length === 0 ? (
          <EmptyState
            title="Nothing due in this view"
            description={
              filter === "all"
                ? "You have no bills, loan repayments or credit card minimums inside the horizon. Add bills or a loan so the plan can reserve the money."
                : "Nothing matches this filter. Switch back to All to see the full list."
            }
          />
        ) : (
          <ul className="mini-list">
            {items.map((item) => (
              <li key={item.id}>
                <div className="mini-list__main">
                  <strong>
                    {item.name}{" "}
                    {item.is_estimate ? <Badge tone="neutral">Estimate</Badge> : null}
                  </strong>
                  <span>
                    {KIND_LABEL[item.kind]}
                    {item.detail ? ` · ${item.detail}` : ""}
                    {item.due_date
                      ? ` · ${formatDate(item.due_date)} (${relativeDueLabel(item.due_date, today)})`
                      : " · no due date"}
                  </span>
                </div>
                <span
                  className={`mini-list__amount ${item.is_overdue ? "amount--negative" : ""}`}
                >
                  {formatMoney(item.amount)}
                </span>
              </li>
            ))}
          </ul>
        )}
      </Card>

      <div className="grid grid--two">
        <Card>
          <h2 style={{ fontSize: "1.02rem", marginBottom: "0.5rem" }}>Income is separate</h2>
          {data.income.sources.length === 0 ? (
            <p className="small muted">No income sources recorded yet.</p>
          ) : (
            <ul className="mini-list">
              {data.income.sources.map((source) => (
                <li key={source.name}>
                  <div className="mini-list__main">
                    <strong>{source.name}</strong>
                    <span>
                      {source.frequency}
                      {source.next_payday ? ` · next ${formatDate(source.next_payday)}` : ""}
                    </span>
                  </div>
                  <span className="mini-list__amount">{formatMoney(source.amount)}</span>
                </li>
              ))}
            </ul>
          )}
          <p className="tiny muted" style={{ marginTop: "0.5rem" }}>{data.income.note}</p>
        </Card>

        <Card>
          <h2 style={{ fontSize: "1.02rem", marginBottom: "0.5rem" }}>Why nothing is double counted</h2>
          <ul className="tiny" style={{ paddingLeft: "1.1rem", lineHeight: 1.8 }}>
            {data.double_counting_guards.map((guard) => (
              <li key={guard}>{guard}</li>
            ))}
          </ul>
          <p className="tiny muted" style={{ marginTop: "0.5rem" }}>
            Bills live on the <Link to="/bills">Bills</Link> page, loan schedules on{" "}
            <Link to="/loans">Loans &amp; advances</Link>, and savings commitments on{" "}
            <Link to="/savings">Savings goals</Link>.
          </p>
        </Card>
      </div>
    </div>
  );
}
