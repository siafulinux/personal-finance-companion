import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { SafeToSpendPanel } from "../components/SafeToSpendPanel";
import {
  Badge,
  Button,
  Card,
  EmptyState,
  ErrorBanner,
  LoadingBlock,
  PageHeader,
  ProgressBar,
} from "../components/ui";
import { useAuth } from "../context/AuthContext";
import { api } from "../lib/api";
import {
  accountTypeLabel,
  formatDate,
  formatMoney,
  formatPercent,
  relativeDueLabel,
  txTypeLabel,
} from "../lib/format";

function greeting(): string {
  const hour = new Date().getHours();
  if (hour < 12) return "Good morning";
  if (hour < 18) return "Good afternoon";
  return "Good evening";
}

export function DashboardPage() {
  const { profile } = useAuth();
  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ["dashboard"],
    queryFn: api.insights.dashboard,
  });

  if (isLoading) return <LoadingBlock label="Building your dashboard" />;
  if (error) {
    return (
      <ErrorBanner
        message={error instanceof Error ? error.message : "Unable to load the dashboard."}
        onRetry={() => void refetch()}
      />
    );
  }
  if (!data) return null;

  const safe = data.safe_to_spend;
  const firstName = profile?.user.display_name.split(" ")[0] ?? "there";
  const maxSpend = Math.max(...data.spending_by_category.map((row) => Number(row.amount)), 1);
  const budget = data.budget;

  return (
    <div className="page-stack">
      {data.is_demo ? (
        <div className="demo-banner" role="status">
          <span>
            <strong>Demo data.</strong> This account is flagged and safe to explore; it never
            mixes with real financial data.
          </span>
          <Link to="/settings" className="link-button">
            Manage demo data
          </Link>
        </div>
      ) : null}

      <PageHeader
        eyebrow={greeting()}
        title={`${firstName}, here is what is actually yours.`}
        description={`Calculated ${formatDate(data.as_of)}. Every figure below comes from your ledger - no estimates, no forecasts in the spend number.`}
        actions={
          <Link to="/shopping" className="btn btn--primary btn--md">
            Start a Shopping Check
          </Link>
        }
      />

      <div className="grid grid--hero">
        <SafeToSpendPanel data={safe} />
        <Card>
          <div className="card__title">
            <h2>Next up</h2>
            {data.pending_match_suggestions > 0 ? (
              <Link to="/bills" className="badge badge--info" style={{ textDecoration: "none" }}>
                {data.pending_match_suggestions} match{data.pending_match_suggestions === 1 ? "" : "es"} to review
              </Link>
            ) : null}
          </div>

          <div className="stat">
            <span className="stat__label">Upcoming bills (14 days)</span>
            <span className="stat__value">{formatMoney(data.upcoming_bills_total)}</span>
            <span className="stat__hint">
              {data.next_payday ? `Next payday ${formatDate(data.next_payday)}` : "No payday configured"}
            </span>
          </div>

          <div className="mini-list" style={{ marginTop: "0.8rem" }}>
            {data.upcoming_bills.slice(0, 4).map((bill) => (
              <li key={bill.id}>
                <div className="mini-list__main">
                  <strong>{bill.bill_name}</strong>
                  <span className={bill.is_overdue ? "amount--negative" : ""}>
                    {relativeDueLabel(bill.due_date, data.today)}
                  </span>
                </div>
                <span className="mini-list__amount">{formatMoney(bill.remaining_amount)}</span>
              </li>
            ))}
            {!data.upcoming_bills.length ? (
              <li>
                <span className="small muted">No bills due in the next two weeks.</span>
              </li>
            ) : null}
          </div>

          <div className="divider" style={{ margin: "0.8rem 0" }} />
          <div className="sts-breakdown" style={{ borderTop: 0, marginTop: 0, paddingTop: 0 }}>
            <span>
              Reserved for later <strong>{formatMoney(data.reserved_total)}</strong>
            </span>
            <span>
              This month net <strong>{formatMoney(data.month_totals.net)}</strong>
            </span>
          </div>
        </Card>
      </div>

      <div className="account-strip">
        {data.accounts.map((account) => (
          <Link
            key={account.id}
            to="/accounts"
            className="account-chip"
            style={{ textDecoration: "none", color: "inherit" }}
          >
            <span className="account-chip__name">
              {accountTypeLabel(account.account_type)}
              {account.include_in_safe_to_spend ? <Badge tone="positive">Counts</Badge> : null}
            </span>
            <strong className="account-chip__amount">{formatMoney(account.balance)}</strong>
            <span className="tiny muted">{account.name}</span>
          </Link>
        ))}
        {!data.accounts.length ? (
          <Card>
            <EmptyState
              title="No accounts yet"
              description="Add a checking or cash account so Safe-to-Spend has something to work with."
              action={
                <Link to="/accounts" className="btn btn--primary btn--md">
                  Add an account
                </Link>
              }
            />
          </Card>
        ) : null}
      </div>

      <div className="dash-grid">
        <div className="page-stack">
          <Card>
            <div className="card__title">
              <div>
                <h2>Spending by category</h2>
                <p className="small muted">This month, posted transactions only</p>
              </div>
              <Link to="/transactions" className="link-button">
                All transactions
              </Link>
            </div>
            {data.spending_by_category.length ? (
              <div className="bar-chart" role="img" aria-label="Spending by category this month">
                {data.spending_by_category.map((row) => {
                  const height = Math.max((Number(row.amount) / maxSpend) * 100, 3);
                  return (
                    <div key={`${row.category_id}-${row.name}`} className="bar-chart__col">
                      <span className="tiny mono muted">{formatMoney(row.amount)}</span>
                      <div
                        className="bar-chart__bar"
                        style={{ height: `${height}%`, background: row.color }}
                        title={`${row.name}: ${formatMoney(row.amount)}`}
                      />
                      <span className="bar-chart__label">{row.name}</span>
                    </div>
                  );
                })}
              </div>
            ) : (
              <EmptyState
                title="No spending recorded yet"
                description="Add a transaction or import a CSV to see where money is going."
                action={
                  <Link to="/transactions" className="btn btn--secondary btn--md">
                    Add a transaction
                  </Link>
                }
              />
            )}
          </Card>

          <Card>
            <div className="card__title">
              <h2>Recent activity</h2>
              <Link to="/transactions" className="link-button">
                View ledger
              </Link>
            </div>
            {data.recent_transactions.length ? (
              <div className="table-wrap">
                <table className="data">
                  <thead>
                    <tr>
                      <th>Description</th>
                      <th>Account</th>
                      <th className="is-right">Amount</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.recent_transactions.map((txn) => (
                      <tr key={txn.id}>
                        <td>
                          <div className="cell-title">
                            <strong>{txn.description}</strong>
                            <span>
                              {formatDate(txn.txn_date)} · {txTypeLabel(txn.tx_type)}
                              {txn.category_name ? ` · ${txn.category_name}` : ""}
                              {txn.status === "pending" ? " · pending" : ""}
                            </span>
                          </div>
                        </td>
                        <td>
                          <span className="small muted">{txn.account_name}</span>
                        </td>
                        <td className="is-right">
                          <span
                            className={`amount ${
                              txn.tx_type === "income" || txn.tx_type === "refund"
                                ? "amount--positive"
                                : txn.tx_type === "transfer"
                                  ? "muted"
                                  : ""
                            }`}
                          >
                            {txn.tx_type === "income" || txn.tx_type === "refund" ? "+" : ""}
                            {formatMoney(txn.amount)}
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <EmptyState
                title="Your ledger is empty"
                description="Record your first transaction, or import a CSV from your bank."
                action={
                  <Link to="/transactions" className="btn btn--secondary btn--md">
                    Get started
                  </Link>
                }
              />
            )}
          </Card>
        </div>

        <div className="page-stack">
          <Card>
            <div className="card__title">
              <h2>Budget pulse</h2>
              <Link to="/budgets" className="link-button">
                {budget ? "Adjust" : "Set up"}
              </Link>
            </div>
            {budget ? (
              <>
                <div className="stat">
                  <span className="stat__label">Remaining this month</span>
                  <span className={`stat__value ${Number(budget.total_remaining) < 0 ? "amount--negative" : ""}`}>
                    {formatMoney(budget.total_remaining)}
                  </span>
                  <span className="stat__hint">
                    {formatMoney(budget.total_spent)} spent of {formatMoney(budget.total_allocated)}
                  </span>
                </div>
                <div style={{ margin: "0.8rem 0" }}>
                  <ProgressBar
                    percent={Number(budget.percent_used)}
                    tone={Number(budget.percent_used) > 100 ? "danger" : Number(budget.percent_used) > 80 ? "warning" : "accent"}
                    label="Budget used"
                  />
                  <p className="tiny muted" style={{ marginTop: "0.3rem" }}>
                    {formatPercent(budget.percent_used)} used
                  </p>
                </div>
                <ul className="mini-list">
                  {budget.rows.slice(0, 4).map((row) => (
                    <li key={row.category_id}>
                      <div className="mini-list__main">
                        <strong>
                          <span
                            className="category-bar__swatch"
                            style={{ background: row.category_color }}
                          />
                          {row.category_name}
                        </strong>
                        <span>
                          {formatMoney(row.spent)} of {formatMoney(row.allocated)}
                        </span>
                      </div>
                      <span
                        className={`mini-list__amount ${
                          Number(row.remaining) < 0 ? "amount--negative" : ""
                        }`}
                      >
                        {formatMoney(row.remaining)}
                      </span>
                    </li>
                  ))}
                </ul>
              </>
            ) : (
              <EmptyState
                title="No budget for this month"
                description="Build one from your income and bills, or copy last month's plan."
                action={
                  <Link to="/budgets" className="btn btn--primary btn--md">
                    Create a budget
                  </Link>
                }
              />
            )}
          </Card>

          <Card>
            <div className="card__title">
              <h2>Upcoming obligations</h2>
              <Link to="/calendar" className="link-button">
                Calendar
              </Link>
            </div>
            {data.upcoming_bills.length ? (
              <div>
                {data.upcoming_bills.slice(0, 6).map((bill) => (
                  <div className="bill-row" key={bill.id}>
                    <div className="bill-row__left">
                      <span className="bill-row__date">{formatDate(bill.due_date, { month: "short", day: "numeric" })}</span>
                      <div>
                        <div className="bill-row__name">{bill.bill_name}</div>
                        <div className="bill-row__sub">
                          {bill.is_overdue ? (
                            <span className="amount--negative">Overdue</span>
                          ) : bill.status === "partial" ? (
                            `Partially paid · ${formatMoney(bill.paid_amount)}`
                          ) : (
                            "Upcoming"
                          )}
                        </div>
                      </div>
                    </div>
                    <span className="mini-list__amount">{formatMoney(bill.remaining_amount)}</span>
                  </div>
                ))}
              </div>
            ) : (
              <p className="small muted">Nothing due in the next two weeks.</p>
            )}
          </Card>

          <Card>
            <h2 style={{ fontSize: "1.02rem", marginBottom: "0.35rem" }}>Before you buy</h2>
            <p className="small muted" style={{ marginBottom: "0.75rem" }}>
              Check a store and category against cash and budget before spending. The answer is
              computed from this ledger, not guessed.
            </p>
            <Link to="/shopping" className="btn btn--secondary btn--md" style={{ width: "100%" }}>
              Open Shopping Check
            </Link>
            <div className="tiny muted" style={{ marginTop: "0.6rem" }}>
              {data.shopping_categories.length} spending categories tracked ·{" "}
              {formatMoney(data.account_totals.total_debt)} credit debt excluded from cash
            </div>
          </Card>
        </div>
      </div>

      {data.warnings.length ? (
        <Card>
          <h2 style={{ fontSize: "1.02rem", marginBottom: "0.6rem" }}>Worth your attention</h2>
          <ul className="warning-list">
            {data.warnings.map((warning) => (
              <li key={warning}>{warning}</li>
            ))}
          </ul>
          <div style={{ marginTop: "0.8rem" }}>
            <Button variant="ghost" size="sm" onClick={() => void refetch()}>
              Recalculate
            </Button>
          </div>
        </Card>
      ) : null}
    </div>
  );
}
