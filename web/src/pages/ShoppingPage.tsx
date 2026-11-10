import { useEffect, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { api } from "../lib/api";
import { formatDate, formatMoney } from "../lib/format";
import type { ShoppingResult } from "../lib/types";
import {
  Badge,
  Button,
  Card,
  Field,
  Input,
  LoadingBlock,
  PageHeader,
  Select,
  Warnings,
} from "../components/ui";
import { SafeToSpendPanel } from "../components/SafeToSpendPanel";
import { ShoppingIntelligence } from "../components/ShoppingIntelligence";

export function ShoppingPage() {
  const categoriesQuery = useQuery({ queryKey: ["categories"], queryFn: () => api.categories.list(false) });
  const dashboardQuery = useQuery({ queryKey: ["dashboard"], queryFn: api.insights.dashboard });
  const [store, setStore] = useState("");
  const [categoryId, setCategoryId] = useState("");
  const [amount, setAmount] = useState("");
  const [note, setNote] = useState("");
  const [result, setResult] = useState<ShoppingResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  const categories = (categoriesQuery.data ?? []).filter((category) => category.kind === "expense");

  useEffect(() => {
    if (!categoryId && categories.length) {
      const clothing = categories.find((category) => category.name === "Clothing");
      setCategoryId(clothing?.id ?? categories[0].id);
    }
  }, [categories, categoryId]);

  const check = useMutation({
    mutationFn: () =>
      api.insights.shopping({
        store_name: store.trim() || "Store",
        category_id: categoryId,
        expected_amount: amount || null,
        note: note || undefined,
      }),
    onSuccess: (data) => {
      setResult(data);
      setError(null);
    },
    onError: (err) => setError(err instanceof Error ? err.message : "Unable to run the check."),
  });

  if (categoriesQuery.isLoading || dashboardQuery.isLoading) {
    return <LoadingBlock label="Loading your buying power" />;
  }

  const dashboard = dashboardQuery.data;
  const categoryAvailability = dashboard?.shopping_categories ?? [];

  return (
    <div className="page-stack">
      <PageHeader
        eyebrow="Shopping Check"
        title="Should you buy it?"
        description="Pick a store and category, add the price, and get a straight answer from your ledger. No AI, no guesses - cash and category limits decide."
      />

      <div className="grid grid--hero">
        <Card>
          <h2 style={{ fontSize: "1.1rem", marginBottom: "0.8rem" }}>Plan a purchase</h2>
          <form
            className="page-stack"
            style={{ gap: "0.9rem" }}
            onSubmit={(event) => {
              event.preventDefault();
              setError(null);
              check.mutate();
            }}
          >
            <div className="form-grid">
              <Field label="Store" htmlFor="shop-store">
                <Input
                  id="shop-store"
                  value={store}
                  onChange={(e) => setStore(e.target.value)}
                  placeholder="Target"
                  maxLength={120}
                />
              </Field>
              <Field label="Category" htmlFor="shop-category">
                <Select
                  id="shop-category"
                  value={categoryId}
                  onChange={(e) => setCategoryId(e.target.value)}
                  required
                >
                  <option value="">Choose a category</option>
                  {categories.map((category) => (
                    <option key={category.id} value={category.id}>
                      {category.name}
                    </option>
                  ))}
                </Select>
              </Field>
              <Field label="Expected amount (optional)" htmlFor="shop-amount">
                <Input
                  id="shop-amount"
                  inputMode="decimal"
                  value={amount}
                  onChange={(e) => setAmount(e.target.value)}
                  placeholder="65.00"
                />
              </Field>
              <Field label="Note (optional)" htmlFor="shop-note">
                <Input
                  id="shop-note"
                  value={note}
                  onChange={(e) => setNote(e.target.value)}
                  placeholder="New running shoes"
                  maxLength={300}
                />
              </Field>
            </div>
            {error ? <div className="form-error" role="alert">{error}</div> : null}
            <Button type="submit" loading={check.isPending} disabled={!categoryId}>
              Check this purchase
            </Button>
          </form>

          <hr className="divider" style={{ margin: "1rem 0" }} />
          <p className="eyebrow">Category headroom</p>
          <ul className="mini-list">
            {categoryAvailability.slice(0, 6).map((category) => (
              <li key={category.category_id}>
                <div className="mini-list__main">
                  <strong>{category.category_name}</strong>
                  <span>
                    {formatMoney(category.spent)} spent of {formatMoney(category.budgeted)}
                    {Number(category.carryover_in) > 0
                      ? ` (+${formatMoney(category.carryover_in)} carried)`
                      : ""}
                  </span>
                </div>
                <span
                  className={`mini-list__amount ${
                    Number(category.remaining) <= 0 ? "amount--negative" : ""
                  }`}
                >
                  {formatMoney(category.remaining)}
                </span>
              </li>
            ))}
          </ul>
        </Card>

        <div className="page-stack">
          {result ? (
            <div className={`shopping-result ${result.purchase && !result.purchase.allowed ? "is-blocked" : ""}`}>
              <p className="eyebrow">
                {result.store_name} · {result.category.category_name}
              </p>
              <p className="shopping-result__verdict">{result.message}</p>

              <div className="metric-grid">
                <div className="stat">
                  <span className="stat__label">Safe to spend</span>
                  <span className="stat__value">{formatMoney(result.safe_to_spend.safe_to_spend)}</span>
                  <span className="stat__hint">Overall cash available now</span>
                </div>
                <div className="stat">
                  <span className="stat__label">{result.category.category_name} remaining</span>
                  <span className="stat__value">{formatMoney(result.category.remaining)}</span>
                  <span className="stat__hint">
                    Max recommended {formatMoney(result.category.max_safe_purchase)}
                  </span>
                </div>
                {result.purchase ? (
                  <div className="stat">
                    <span className="stat__label">After this purchase</span>
                    <span
                      className={`stat__value ${
                        Number(result.purchase.category_remaining_after) < 0 ? "amount--negative" : ""
                      }`}
                    >
                      {formatMoney(result.purchase.category_remaining_after)}
                    </span>
                    <span className="stat__hint">in {result.category.category_name}</span>
                  </div>
                ) : null}
                <div className="stat">
                  <span className="stat__label">Next payday</span>
                  <span className="stat__value" style={{ fontSize: "1.05rem" }}>
                    {result.next_payday ? formatDate(result.next_payday) : "Not set"}
                  </span>
                  <span className="stat__hint">
                    Bills reserved through {formatDate(result.safe_to_spend.horizon_end)}
                  </span>
                </div>
              </div>

              <div style={{ marginTop: "1rem" }}>
                {result.purchase?.allowed ? (
                  <Badge tone="positive">Fits your plan</Badge>
                ) : (
                  <Badge tone="danger">Not recommended</Badge>
                )}{" "}
                {result.bills_covered ? (
                  <Badge tone="positive">Upcoming bills covered</Badge>
                ) : (
                  <Badge tone="danger">
                    Projected shortfall {formatMoney(result.projected_shortfall)}
                  </Badge>
                )}
              </div>

              <div style={{ marginTop: "1rem" }}>
                <p className="eyebrow">Upcoming bills in this horizon</p>
                {result.upcoming_bills.length ? (
                  <ul className="mini-list">
                    {result.upcoming_bills.slice(0, 5).map((bill) => (
                      <li key={bill.id}>
                        <div className="mini-list__main">
                          <strong>{bill.bill_name}</strong>
                          <span>{formatDate(bill.due_date)}</span>
                        </div>
                        <span className="mini-list__amount">{formatMoney(bill.remaining_amount)}</span>
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="small muted">No unpaid bills inside the planning horizon.</p>
                )}
              </div>

              {result.warnings.length ? (
                <div style={{ marginTop: "1rem" }}>
                  <Warnings items={result.warnings} />
                </div>
              ) : null}

              <p className="tiny muted" style={{ marginTop: "0.8rem" }}>
                Calculated {formatDate(result.as_of)} · figures come from the same
                engine as your dashboard.
              </p>
            </div>
          ) : (
            <Card>
              <p className="eyebrow">How answers are made</p>
              <h2 style={{ fontSize: "1.2rem", marginBottom: "0.6rem" }}>
                Cash first. Category second.
              </h2>
              <p className="small muted" style={{ marginBottom: "0.8rem" }}>
                A healthy clothing budget cannot spend money that is already reserved for rent. The
                recommended maximum is always the smaller of your overall Safe-to-Spend and the
                category&apos;s remaining budget.
              </p>
              {dashboard ? (
                <SafeToSpendPanel data={dashboard.safe_to_spend} compact showExplanation={false} />
              ) : null}
            </Card>
          )}

          {dashboard ? (
            <Card>
              <h2 style={{ fontSize: "1.02rem", marginBottom: "0.5rem" }}>Context</h2>
              <div className="sts-breakdown" style={{ borderTop: 0, marginTop: 0, paddingTop: 0 }}>
                <span>
                  Next payday{" "}
                  <strong>{dashboard.next_payday ? formatDate(dashboard.next_payday) : "not set"}</strong>
                </span>
                <span>
                  Bills due in 14 days <strong>{formatMoney(dashboard.upcoming_bills_total)}</strong>
                </span>
                <span>
                  Reserved savings <strong>{formatMoney(dashboard.reserved_total)}</strong>
                </span>
              </div>
              <p className="tiny muted" style={{ marginTop: "0.6rem" }}>
                Location features live in the Android app and are opt-in. This screen works
                anywhere, and no browser reads your position.
              </p>
            </Card>
          ) : null}
        </div>
      </div>

      <ShoppingIntelligence />
    </div>
  );
}
