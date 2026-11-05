import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../lib/api";
import {
  addDaysISO,
  formatDate,
  formatMoney,
  formatPercent,
  frequencyLabel,
  relativeDueLabel,
  todayISO,
} from "../lib/format";
import type { Bill, Occurrence } from "../lib/types";
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
  Select,
  Textarea,
} from "../components/ui";

type Tab = "upcoming" | "overdue" | "paid" | "bills";

/** Upcoming shows a rolling window so a long bill schedule stays readable. */
const UPCOMING_WINDOW_DAYS = 90;

function statusLabel(status: string): string {
  const labels: Record<string, string> = {
    upcoming: "Upcoming",
    partial: "Partial",
    paid: "Paid",
    skipped: "Skipped",
  };
  return labels[status] ?? status;
}

interface BillForm {
  name: string;
  merchant: string;
  expected_amount: string;
  minimum_amount: string;
  first_due_date: string;
  frequency: string;
  custom_interval_days: string;
  account_id: string;
  category_id: string;
  notes: string;
  is_essential: boolean;
  reserve_in_safe_to_spend: boolean;
  is_active: boolean;
}

const blankBill = (): BillForm => ({
  name: "",
  merchant: "",
  expected_amount: "",
  minimum_amount: "",
  first_due_date: todayISO(),
  frequency: "monthly",
  custom_interval_days: "",
  account_id: "",
  category_id: "",
  notes: "",
  is_essential: true,
  reserve_in_safe_to_spend: true,
  is_active: true,
});

export function BillsPage() {
  const queryClient = useQueryClient();
  const [tab, setTab] = useState<Tab>("upcoming");
  const [formOpen, setFormOpen] = useState(false);
  const [editing, setEditing] = useState<Bill | null>(null);
  const [form, setForm] = useState<BillForm>(blankBill());
  const [formError, setFormError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [paying, setPaying] = useState<Occurrence | null>(null);
  const [paymentAmount, setPaymentAmount] = useState("");
  const [paymentAccount, setPaymentAccount] = useState("");
  const [paymentDate, setPaymentDate] = useState(todayISO());
  const [paymentError, setPaymentError] = useState<string | null>(null);
  const [deletingBill, setDeletingBill] = useState<Bill | null>(null);
  const [markPaidTarget, setMarkPaidTarget] = useState<Occurrence | null>(null);

  const accountsQuery = useQuery({ queryKey: ["accounts", false], queryFn: () => api.accounts.list(false) });
  const categoriesQuery = useQuery({ queryKey: ["categories"], queryFn: () => api.categories.list(false) });
  const occurrencesQuery = useQuery({
    queryKey: ["bill-occurrences"],
    queryFn: () => api.bills.occurrences({ limit: 300 }),
  });
  const billsQuery = useQuery({
    queryKey: ["bills"],
    queryFn: () => api.bills.list(false),
  });
  const suggestionsQuery = useQuery({
    queryKey: ["match-suggestions"],
    queryFn: api.bills.suggestions,
  });

  const accounts = accountsQuery.data?.accounts ?? [];
  const categories = categoriesQuery.data ?? [];

  const invalidate = () => {
    void queryClient.invalidateQueries({ queryKey: ["bill-occurrences"] });
    void queryClient.invalidateQueries({ queryKey: ["bills"] });
    void queryClient.invalidateQueries({ queryKey: ["match-suggestions"] });
    void queryClient.invalidateQueries({ queryKey: ["dashboard"] });
    void queryClient.invalidateQueries({ queryKey: ["safe-to-spend"] });
    void queryClient.invalidateQueries({ queryKey: ["budget"] });
  };

  const saveBill = useMutation({
    mutationFn: async () => {
      const payload: Record<string, unknown> = {
        name: form.name,
        merchant: form.merchant || null,
        expected_amount: form.expected_amount,
        minimum_amount: form.minimum_amount || null,
        frequency: form.frequency,
        custom_interval_days:
          form.frequency === "custom" && form.custom_interval_days
            ? Number(form.custom_interval_days)
            : null,
        account_id: form.account_id || null,
        category_id: form.category_id || null,
        notes: form.notes || null,
        is_essential: form.is_essential,
        reserve_in_safe_to_spend: form.reserve_in_safe_to_spend,
        is_active: form.is_active,
      };
      if (!editing) {
        payload.anchor_date = form.first_due_date;
      }
      return editing ? api.bills.update(editing.id, payload) : api.bills.create(payload);
    },
    onSuccess: () => {
      setFormOpen(false);
      setEditing(null);
      invalidate();
    },
    onError: (err) => setFormError(err instanceof Error ? err.message : "Unable to save the bill."),
  });

  const markPaid = useMutation({
    mutationFn: (id: string) => api.bills.markPaid(id),
    onSuccess: () => {
      setMarkPaidTarget(null);
      invalidate();
    },
    onError: (err) => {
      setMarkPaidTarget(null);
      setActionError(err instanceof Error ? err.message : "Unable to mark this bill paid.");
    },
  });

  const markUnpaid = useMutation({
    mutationFn: (id: string) => api.bills.markUnpaid(id),
    onSuccess: invalidate,
    onError: (err) => setActionError(err instanceof Error ? err.message : "Unable to reopen this bill."),
  });

  const skip = useMutation({
    mutationFn: (id: string) => api.bills.skip(id),
    onSuccess: invalidate,
    onError: (err) => setActionError(err instanceof Error ? err.message : "Unable to skip this occurrence."),
  });

  const recordPayment = useMutation({
    mutationFn: async () => {
      if (!paying) throw new Error("No bill selected.");
      return api.bills.recordPayment(paying.id, {
        account_id: paymentAccount,
        amount: paymentAmount || undefined,
        paid_on: paymentDate,
      });
    },
    onSuccess: () => {
      setPaying(null);
      invalidate();
    },
    onError: (err) => setPaymentError(err instanceof Error ? err.message : "Unable to record payment."),
  });

  const toggleBill = useMutation({
    mutationFn: (bill: Bill) => api.bills.update(bill.id, { is_active: !bill.is_active }),
    onSuccess: invalidate,
    onError: (err) => setActionError(err instanceof Error ? err.message : "Unable to update the bill."),
  });

  const deleteBill = useMutation({
    mutationFn: (id: string) => api.bills.remove(id),
    onSuccess: () => {
      setDeletingBill(null);
      invalidate();
    },
    onError: (err) => {
      setDeletingBill(null);
      setActionError(err instanceof Error ? err.message : "Unable to delete the bill.");
    },
  });

  const confirmMatch = useMutation({
    mutationFn: (matchId: string) => api.bills.confirmMatch(matchId),
    onSuccess: invalidate,
    onError: (err) => setActionError(err instanceof Error ? err.message : "Unable to confirm the match."),
  });

  const rejectMatch = useMutation({
    mutationFn: (matchId: string) => api.bills.rejectMatch(matchId),
    onSuccess: invalidate,
    onError: (err) => setActionError(err instanceof Error ? err.message : "Unable to reject the match."),
  });

  const occurrences = occurrencesQuery.data ?? [];
  const today = todayISO();
  const filtered = useMemo(() => {
    const sorted = [...occurrences].sort((a, b) => a.due_date.localeCompare(b.due_date));
    if (tab === "overdue") return sorted.filter((o) => o.is_overdue);
    if (tab === "paid") return sorted.filter((o) => o.status === "paid").reverse();
    if (tab === "upcoming") {
      const horizon = addDaysISO(today, UPCOMING_WINDOW_DAYS);
      return sorted.filter(
        (o) =>
          !o.is_overdue &&
          o.status !== "paid" &&
          o.status !== "skipped" &&
          o.due_date <= horizon
      );
    }
    return sorted;
  }, [occurrences, tab]);

  const openCreate = () => {
    setEditing(null);
    setForm(blankBill());
    setFormError(null);
    setFormOpen(true);
  };

  const openEdit = (bill: Bill) => {
    setEditing(bill);
    setForm({
      name: bill.name,
      merchant: bill.merchant ?? "",
      expected_amount: bill.expected_amount,
      minimum_amount: bill.minimum_amount ?? "",
      first_due_date: bill.anchor_date,
      frequency: bill.frequency,
      custom_interval_days: bill.custom_interval_days ? String(bill.custom_interval_days) : "",
      account_id: bill.account_id ?? "",
      category_id: bill.category_id ?? "",
      notes: bill.notes ?? "",
      is_essential: bill.is_essential,
      reserve_in_safe_to_spend: bill.reserve_in_safe_to_spend,
      is_active: bill.is_active,
    });
    setFormError(null);
    setFormOpen(true);
  };

  const bills = billsQuery.data?.items ?? [];
  const suggestions = suggestionsQuery.data?.items ?? [];

  return (
    <div className="page-stack">
      <PageHeader
        eyebrow="Bills"
        title="Recurring obligations, handled"
        description="Each bill generates real occurrences. Match payments deterministically, confirm partial payments, and keep reserves in sync with Safe-to-Spend."
        actions={<Button onClick={openCreate}>Add a bill</Button>}
      />

      {actionError ? <ErrorBanner message={actionError} /> : null}

      {suggestions.length ? (
        <Card>
          <div className="card__title">
            <div>
              <h2>Payments to confirm</h2>
              <p className="small muted">
                These are suggestions, never automatic. Ambiguous matches require your judgment.
              </p>
            </div>
            <Badge tone="info">{suggestions.length} transaction(s)</Badge>
          </div>
          <div className="page-stack" style={{ gap: "0.8rem" }}>
            {suggestions.map((group) => (
              <div key={group.transaction_id} className="summary-strip" style={{ alignItems: "flex-start" }}>
                <div style={{ flex: "1 1 240px" }}>
                  <strong>{group.transaction_description}</strong>
                  <div className="tiny muted">
                    {formatDate(group.transaction_date)} · {formatMoney(group.transaction_amount)}
                    {group.transaction_merchant ? ` · ${group.transaction_merchant}` : ""}
                  </div>
                </div>
                <div style={{ flex: "2 1 320px", display: "flex", flexDirection: "column", gap: "0.4rem" }}>
                  {group.candidates.map((candidate) => (
                    <div
                      key={candidate.match_id}
                      style={{ display: "flex", gap: "0.5rem", alignItems: "center", flexWrap: "wrap" }}
                    >
                      <span>
                        {candidate.bill_name} · due {formatDate(candidate.due_date)} ·{" "}
                        {formatMoney(candidate.remaining)} remaining
                      </span>
                      <Badge tone={Number(candidate.confidence) >= 0.85 ? "positive" : "warning"}>
                        {formatPercent(Number(candidate.confidence) * 100)} confidence
                      </Badge>
                      {candidate.is_ambiguous ? <Badge tone="warning">Ambiguous</Badge> : null}
                      <Button
                        size="sm"
                        onClick={() => confirmMatch.mutate(candidate.match_id)}
                        loading={confirmMatch.isPending}
                      >
                        Confirm
                      </Button>
                      <Button
                        size="sm"
                        variant="ghost"
                        onClick={() => rejectMatch.mutate(candidate.match_id)}
                        loading={rejectMatch.isPending}
                      >
                        Not this
                      </Button>
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </Card>
      ) : null}

      <div className="tabs" role="tablist" aria-label="Bill views">
        {(
          [
            ["upcoming", "Upcoming"],
            ["overdue", "Overdue"],
            ["paid", "Paid"],
            ["bills", "Recurring bills"],
          ] as [Tab, string][]
        ).map(([value, label]) => (
          <button
            key={value}
            type="button"
            role="tab"
            aria-selected={tab === value}
            className={`tab ${tab === value ? "is-active" : ""}`}
            onClick={() => setTab(value)}
          >
            {label}
            {value === "overdue" && occurrences.some((o) => o.is_overdue) ? (
              <span className="badge badge--danger" style={{ marginLeft: "0.35rem" }}>
                {occurrences.filter((o) => o.is_overdue).length}
              </span>
            ) : null}
          </button>
        ))}
      </div>

      {tab !== "bills" ? (
        <Card className="card--flush">
          {occurrencesQuery.isLoading ? (
            <div style={{ padding: "1.2rem" }}>
              <LoadingBlock label="Loading bill occurrences" />
            </div>
          ) : filtered.length ? (
            <div className="table-wrap">
              <table className="data">
                <thead>
                  <tr>
                    <th>Bill</th>
                    <th>Due</th>
                    <th>Status</th>
                    <th className="is-right">Expected</th>
                    <th className="is-right">Paid</th>
                    <th className="is-right">Remaining</th>
                    <th className="is-right">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {filtered.map((occurrence) => (
                    <tr key={occurrence.id}>
                      <td>
                        <div className="cell-title">
                          <strong>{occurrence.bill_name}</strong>
                          <span>
                            {occurrence.merchant ?? "No merchant"}
                            {occurrence.is_essential ? " · essential" : ""}
                          </span>
                        </div>
                      </td>
                      <td>
                        <div className="cell-title">
                          <strong style={{ fontWeight: 500 }}>{formatDate(occurrence.due_date)}</strong>
                          <span className={occurrence.is_overdue ? "amount--negative" : ""}>
                            {relativeDueLabel(occurrence.due_date, today)}
                          </span>
                        </div>
                      </td>
                      <td>
                        <Badge
                          tone={
                            occurrence.status === "paid"
                              ? "positive"
                              : occurrence.status === "partial"
                                ? "warning"
                                : occurrence.is_overdue
                                  ? "danger"
                                  : "neutral"
                          }
                        >
                          {occurrence.is_overdue ? "Overdue" : statusLabel(occurrence.status)}
                        </Badge>
                      </td>
                      <td className="is-right mono">{formatMoney(occurrence.expected_amount)}</td>
                      <td className="is-right mono">{formatMoney(occurrence.paid_amount)}</td>
                      <td className="is-right mono">{formatMoney(occurrence.remaining_amount)}</td>
                      <td>
                        <div className="row-actions">
                          {occurrence.status !== "paid" ? (
                            <>
                              <Button
                                size="sm"
                                onClick={() => {
                                  setPaying(occurrence);
                                  setPaymentAmount(occurrence.remaining_amount);
                                  setPaymentAccount(occurrence.account_id ?? accounts[0]?.id ?? "");
                                  setPaymentDate(todayISO());
                                  setPaymentError(null);
                                }}
                                disabled={!accounts.length}
                              >
                                Pay
                              </Button>
                              <Button
                                size="sm"
                                variant="secondary"
                                onClick={() => setMarkPaidTarget(occurrence)}
                              >
                                Mark paid
                              </Button>
                              <Button
                                size="sm"
                                variant="ghost"
                                onClick={() => skip.mutate(occurrence.id)}
                                loading={skip.isPending}
                              >
                                Skip
                              </Button>
                            </>
                          ) : (
                            <Button
                              size="sm"
                              variant="ghost"
                              onClick={() => markUnpaid.mutate(occurrence.id)}
                              loading={markUnpaid.isPending}
                            >
                              Reopen
                            </Button>
                          )}
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <EmptyState
              title={tab === "overdue" ? "Nothing overdue" : tab === "paid" ? "No paid bills yet" : "No upcoming bills"}
              description={
                tab === "overdue"
                  ? "Every occurrence is either paid, upcoming, or skipped."
                  : "Add a recurring bill to generate occurrences and reserves automatically."
              }
              action={<Button onClick={openCreate}>Add a bill</Button>}
            />
          )}
        </Card>
      ) : (
        <Card className="card--flush">
          {bills.length ? (
            <div className="table-wrap">
              <table className="data">
                <thead>
                  <tr>
                    <th>Bill</th>
                    <th>Frequency</th>
                    <th>Next due</th>
                    <th className="is-right">Amount</th>
                    <th>Reserve</th>
                    <th className="is-right">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {bills.map((bill) => (
                    <tr key={bill.id}>
                      <td>
                        <div className="cell-title">
                          <strong>{bill.name}</strong>
                          <span>
                            {bill.merchant ?? "No merchant"}
                            {bill.is_essential ? " · essential" : ""}
                            {!bill.is_active ? " · inactive" : ""}
                          </span>
                        </div>
                      </td>
                      <td className="small">{frequencyLabel(bill.frequency)}</td>
                      <td className="mono tiny">
                        {bill.next_due_date ? formatDate(bill.next_due_date) : "—"}
                        {bill.is_overdue ? <Badge tone="danger">Overdue</Badge> : null}
                      </td>
                      <td className="is-right mono">{formatMoney(bill.expected_amount)}</td>
                      <td>
                        <Badge tone={bill.reserve_in_safe_to_spend ? "positive" : "neutral"}>
                          {bill.reserve_in_safe_to_spend ? "Reserved" : "Not reserved"}
                        </Badge>
                      </td>
                      <td>
                        <div className="row-actions">
                          <Button size="sm" variant="ghost" onClick={() => openEdit(bill)}>
                            Edit
                          </Button>
                          <Button
                            size="sm"
                            variant="ghost"
                            onClick={() => toggleBill.mutate(bill)}
                            loading={toggleBill.isPending}
                          >
                            {bill.is_active ? "Pause" : "Resume"}
                          </Button>
                          <Button size="sm" variant="ghost" onClick={() => setDeletingBill(bill)}>
                            Delete
                          </Button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <EmptyState
              title="No recurring bills yet"
              description="Add rent, utilities, subscriptions or any repeating obligation. Occurrences are generated automatically."
              action={<Button onClick={openCreate}>Add your first bill</Button>}
            />
          )}
        </Card>
      )}

      <p className="tiny muted">
        {tab === "upcoming"
          ? `Upcoming covers the next ${UPCOMING_WINDOW_DAYS} days; later occurrences appear as they get closer.`
          : null}
        {" "}
        Automatic matching is {suggestions.length ? "reviewing" : "on"} for posted purchases and bill
        payments. Configure thresholds and tolerances in Settings. High-confidence unique matches mark
        bills paid; ambiguous ones always wait for you.
      </p>

      <Modal
        open={formOpen}
        title={editing ? "Edit bill" : "Add a recurring bill"}
        description="Expected amount drives the reserve. Minimum amount is used only as context for variable bills."
        onClose={() => setFormOpen(false)}
        wide
        footer={
          <>
            <Button variant="ghost" type="button" onClick={() => setFormOpen(false)}>
              Cancel
            </Button>
            <Button
              type="button"
              loading={saveBill.isPending}
              onClick={() => {
                setFormError(null);
                if (!form.name.trim()) return setFormError("Give this bill a name.");
                if (!form.expected_amount || Number(form.expected_amount) <= 0)
                  return setFormError("Enter the expected amount.");
                saveBill.mutate();
              }}
            >
              {editing ? "Save bill" : "Create bill"}
            </Button>
          </>
        }
      >
        <div className="form-grid">
          <Field label="Bill name" htmlFor="bill-name">
            <Input
              id="bill-name"
              value={form.name}
              onChange={(e) => setForm({ ...form, name: e.target.value })}
              placeholder="Internet"
              maxLength={120}
            />
          </Field>
          <Field label="Merchant" hint="Used for payment matching." htmlFor="bill-merchant">
            <Input
              id="bill-merchant"
              value={form.merchant}
              onChange={(e) => setForm({ ...form, merchant: e.target.value })}
              placeholder="Comcast"
              maxLength={160}
            />
          </Field>
          <Field label="Expected amount" htmlFor="bill-amount">
            <Input
              id="bill-amount"
              inputMode="decimal"
              value={form.expected_amount}
              onChange={(e) => setForm({ ...form, expected_amount: e.target.value })}
              placeholder="85.00"
            />
          </Field>
          <Field label="Minimum amount (optional)" htmlFor="bill-min">
            <Input
              id="bill-min"
              inputMode="decimal"
              value={form.minimum_amount}
              onChange={(e) => setForm({ ...form, minimum_amount: e.target.value })}
            />
          </Field>
          <Field label={editing ? "First due date (anchor)" : "First due date"} htmlFor="bill-date">
            <Input
              id="bill-date"
              type="date"
              value={form.first_due_date}
              onChange={(e) => setForm({ ...form, first_due_date: e.target.value })}
              disabled={Boolean(editing)}
            />
          </Field>
          <Field label="Frequency" htmlFor="bill-frequency">
            <Select
              id="bill-frequency"
              value={form.frequency}
              onChange={(e) => setForm({ ...form, frequency: e.target.value })}
            >
              <option value="weekly">Weekly</option>
              <option value="biweekly">Every 2 weeks</option>
              <option value="monthly">Monthly</option>
              <option value="every_two_months">Every 2 months</option>
              <option value="quarterly">Quarterly</option>
              <option value="semiannual">Every 6 months</option>
              <option value="annual">Yearly</option>
              <option value="custom">Custom interval</option>
            </Select>
          </Field>
          {form.frequency === "custom" ? (
            <Field label="Custom interval (days)" htmlFor="bill-interval">
              <Input
                id="bill-interval"
                inputMode="numeric"
                value={form.custom_interval_days}
                onChange={(e) => setForm({ ...form, custom_interval_days: e.target.value })}
              />
            </Field>
          ) : null}
          <Field label="Payment account" htmlFor="bill-account">
            <Select
              id="bill-account"
              value={form.account_id}
              onChange={(e) => setForm({ ...form, account_id: e.target.value })}
            >
              <option value="">Any account</option>
              {accounts.map((account) => (
                <option key={account.id} value={account.id}>
                  {account.name}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="Category" htmlFor="bill-category">
            <Select
              id="bill-category"
              value={form.category_id}
              onChange={(e) => setForm({ ...form, category_id: e.target.value })}
            >
              <option value="">Uncategorized</option>
              {categories.map((category) => (
                <option key={category.id} value={category.id}>
                  {category.name}
                </option>
              ))}
            </Select>
          </Field>
          <div className="span-2">
            <Field label="Notes" htmlFor="bill-notes">
              <Textarea
                id="bill-notes"
                value={form.notes}
                onChange={(e) => setForm({ ...form, notes: e.target.value })}
              />
            </Field>
          </div>
        </div>
        <label className="checkbox">
          <input
            type="checkbox"
            checked={form.reserve_in_safe_to_spend}
            onChange={(e) => setForm({ ...form, reserve_in_safe_to_spend: e.target.checked })}
          />
          Reserve this bill in Safe-to-Spend until it is paid
        </label>
        <label className="checkbox">
          <input
            type="checkbox"
            checked={form.is_essential}
            onChange={(e) => setForm({ ...form, is_essential: e.target.checked })}
          />
          Essential (rent, utilities, insurance)
        </label>
        {editing ? (
          <label className="checkbox">
            <input
              type="checkbox"
              checked={form.is_active}
              onChange={(e) => setForm({ ...form, is_active: e.target.checked })}
            />
            Active — inactive bills stop generating occurrences and reserves
          </label>
        ) : null}
        {formError ? <div className="form-error">{formError}</div> : null}
      </Modal>

      <Modal
        open={Boolean(paying)}
        title="Record a bill payment"
        description="Creates a bill-payment transaction from the selected account and links it to this occurrence."
        onClose={() => setPaying(null)}
        footer={
          <>
            <Button variant="ghost" type="button" onClick={() => setPaying(null)}>
              Cancel
            </Button>
            <Button
              type="button"
              loading={recordPayment.isPending}
              onClick={() => {
                setPaymentError(null);
                if (!paymentAccount) return setPaymentError("Choose the account you paid from.");
                recordPayment.mutate();
              }}
            >
              Record payment
            </Button>
          </>
        }
      >
        <p className="small muted">
          {paying?.bill_name} · due {paying ? formatDate(paying.due_date) : ""} ·{" "}
          {paying ? formatMoney(paying.remaining_amount) : ""} remaining
        </p>
        <Field label="Account" htmlFor="pay-account">
          <Select
            id="pay-account"
            value={paymentAccount}
            onChange={(e) => setPaymentAccount(e.target.value)}
          >
            {accounts.map((account) => (
              <option key={account.id} value={account.id}>
                {account.name}
              </option>
            ))}
          </Select>
        </Field>
        <Field label="Amount" hint="Less than the remainder creates a partial payment." htmlFor="pay-amount">
          <Input
            id="pay-amount"
            inputMode="decimal"
            value={paymentAmount}
            onChange={(e) => setPaymentAmount(e.target.value)}
          />
        </Field>
        <Field label="Paid on" htmlFor="pay-date">
          <Input
            id="pay-date"
            type="date"
            value={paymentDate}
            onChange={(e) => setPaymentDate(e.target.value)}
          />
        </Field>
        {paymentError ? <div className="form-error">{paymentError}</div> : null}
      </Modal>

      <ConfirmDialog
        open={Boolean(markPaidTarget)}
        title="Mark this bill paid?"
        message={
          <>
            This records {markPaidTarget?.bill_name} as fully paid without creating a transaction.
            Use it for bills already paid outside your tracked accounts.
          </>
        }
        confirmLabel="Mark paid"
        busy={markPaid.isPending}
        onConfirm={() => markPaidTarget && markPaid.mutate(markPaidTarget.id)}
        onCancel={() => setMarkPaidTarget(null)}
      />

      <ConfirmDialog
        open={Boolean(deletingBill)}
        title="Delete this bill?"
        message={
          <>
            <strong>{deletingBill?.name}</strong> and its occurrence schedule will be removed. Bills
            with confirmed payments cannot be deleted; pause them instead.
          </>
        }
        confirmLabel="Delete bill"
        destructive
        busy={deleteBill.isPending}
        onConfirm={() => deletingBill && deleteBill.mutate(deletingBill.id)}
        onCancel={() => setDeletingBill(null)}
      />
    </div>
  );
}
