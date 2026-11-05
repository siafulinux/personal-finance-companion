import { useState } from "react";
import { formatDate, formatMoney } from "../lib/format";
import type { SafeToSpend } from "../lib/types";
import { Badge, Warnings } from "./ui";

export function SafeToSpendPanel({
  data,
  compact = false,
  showExplanation = true,
}: {
  data: SafeToSpend;
  compact?: boolean;
  showExplanation?: boolean;
}) {
  const [open, setOpen] = useState(false);
  const zero = Number(data.safe_to_spend) <= 0;

  return (
    <div className="card card--hero">
      <div className="card__title">
        <div>
          <p className="eyebrow" style={{ marginBottom: "0.15rem" }}>
            Safe to spend
          </p>
          {data.payday ? (
            <span className="small muted">Until your next payday · {formatDate(data.payday)}</span>
          ) : (
            <span className="small muted">
              Planning horizon · through {formatDate(data.horizon_end)}
            </span>
          )}
        </div>
        <span className="sts-asof">{new Date(data.as_of).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}</span>
      </div>

      <p className={`sts-amount ${zero ? "sts-amount--zero" : ""}`}>{formatMoney(data.safe_to_spend)}</p>
      <p className="sts-caption">
        {zero
          ? "Every available dollar is already committed. Shortfall is shown below."
          : "Spendable now without touching bills, buffers or reserves."}
      </p>

      <div className="sts-breakdown">
        <span>
          Available <strong>{formatMoney(data.eligible_balance)}</strong>
        </span>
        <span>
          Pending <strong>-{formatMoney(data.pending_debits)}</strong>
        </span>
        <span>
          Bills reserved <strong>-{formatMoney(data.bill_reserves)}</strong>
        </span>
        <span>
          Buffer <strong>-{formatMoney(data.minimum_buffer)}</strong>
        </span>
        <span>
          Reserves <strong>-{formatMoney(data.explicit_reserves)}</strong>
        </span>
      </div>

      {Number(data.projected_shortfall) > 0 ? (
        <p className="badge badge--danger" style={{ marginTop: "0.8rem" }}>
          Projected shortfall {formatMoney(data.projected_shortfall)}
        </p>
      ) : null}

      {!compact && data.warnings.length ? (
        <div style={{ marginTop: "0.9rem" }}>
          <Warnings items={data.warnings} />
        </div>
      ) : data.warnings.length ? (
        <p className="tiny" style={{ marginTop: "0.7rem", color: "var(--amber)" }}>
          {data.warnings[0]}
        </p>
      ) : null}

      {showExplanation ? (
        <div style={{ marginTop: "0.9rem" }}>
          <button type="button" className="link-button" onClick={() => setOpen((v) => !v)}>
            {open ? "Hide calculation" : "How this is calculated"}
          </button>
          {open ? (
            <div style={{ marginTop: "0.7rem" }}>
              <ul className="explain-list">
                {data.explanation.map((line) => (
                  <li key={line.key} className={line.kind === "result" ? "is-result" : ""}>
                    <span className="explain-list__label">
                      {line.label}
                      {line.detail ? (
                        <span className="tiny muted" style={{ display: "block" }}>
                          {line.detail}
                        </span>
                      ) : null}
                    </span>
                    <span className="explain-list__amount">
                      {line.kind === "debit" ? "-" : ""}
                      {formatMoney(line.amount)}
                    </span>
                  </li>
                ))}
              </ul>
              <div className="sts-breakdown" style={{ marginTop: "0.7rem" }}>
                <span>
                  Accounts:{" "}
                  <strong>
                    {data.accounts.map((account) => account.name).join(", ") || "none"}
                  </strong>
                </span>
                <span>
                  Pending items: <strong>{data.pending_items.length}</strong>
                </span>
                <span>
                  Bills reserved: <strong>{data.bills.length}</strong>
                </span>
                {data.stale_information ? (
                  <Badge tone="warning">Balances may be stale</Badge>
                ) : (
                  <Badge tone="positive">Balances fresh</Badge>
                )}
              </div>
            </div>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
