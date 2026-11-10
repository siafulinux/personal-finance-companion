import { useState, type FormEvent } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../lib/api";
import { formatDate, formatMoney, formatPercent, todayISO } from "../lib/format";
import type { Loan } from "../lib/types";
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

const LOAN_TYPES: { value: string; label: string }[] = [
  { value: "personal", label: "Personal loan" },
  { value: "payday", label: "Payday loan" },
  { value: "cash_advance", label: "Cash advance" },
  { value: "earned_wage_access", label: "Earned wage access" },
  { value: "buy_now_pay_later", label: "Buy now, pay later" },
  { value: "installment", label: "Installment plan" },
  { value: "credit_agreement", label: "Credit agreement" },
  { value: "other", label: "Other borrowing" },
];

interface LoanForm {
  name: string;
  lender: string;
  loan_type: string;
  original_amount: string;
  opening_balance: string;
  balance_as_of: string;
  apr: string;
  next_payment_date: string;
  scheduled_payment: string;
  payment_frequency: string;
  remaining_payments: string;
  notes: string;
}

const emptyForm = (): LoanForm => ({
  name: "",
  lender: "",
  loan_type: "personal",
  original_amount: "",
  opening_balance: "",
  balance_as_of: todayISO(),
  apr: "",
  next_payment_date: "",
  scheduled_payment: "",
  payment_frequency: "monthly",
  remaining_payments: "",
  notes: "",
});

export function LoansPage() {
  const queryClient = useQueryClient();
  const [formOpen, setFormOpen] = useState(false);
  const [editing, setEditing] = useState<Loan | null>(null);
  const [form, setForm] = useState<LoanForm>(emptyForm());
  const [formError, setFormError] = useState<string | null>(null);
  const [paying, setPaying] = useState<Loan | null>(null);
  const [payment, setPayment] = useState({ amount: "", paid_on: todayISO(), principal: "", interest: "", fee: "" });
  const [paymentError, setPaymentError] = useState<string | null>(null);
  const [matching, setMatching] = useState<Loan | null>(null);
  const [deleting, setDeleting] = useState<Loan | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  const loansQuery = useQuery({ queryKey: ["loans"], queryFn: api.loans.list });
  const suggestionsQuery = useQuery({
    queryKey: ["loan-suggestions", matching?.id],
    queryFn: () => api.loans.suggestions(matching!.id),
    enabled: Boolean(matching?.id),
  });

  const invalidate = () => {
    void queryClient.invalidateQueries({ queryKey: ["loans"] });
    void queryClient.invalidateQueries({ queryKey: ["loan-suggestions"] });
    void queryClient.invalidateQueries({ queryKey: ["obligations"] });
    void queryClient.invalidateQueries({ queryKey: ["safe-to-spend"] });
    void queryClient.invalidateQueries({ queryKey: ["dashboard"] });
  };

  const saveMutation = useMutation({
    mutationFn: async () => {
      const body = {
        name: form.name,
        lender: form.lender || null,
        loan_type: form.loan_type,
        original_amount: form.original_amount,
        opening_balance: form.opening_balance,
        balance_as_of: form.balance_as_of || null,
        apr: form.apr || null,
        next_payment_date: form.next_payment_date || null,
        scheduled_payment: form.scheduled_payment || null,
        payment_frequency: form.scheduled_payment ? form.payment_frequency : null,
        remaining_payments: form.remaining_payments ? Number(form.remaining_payments) : null,
        notes: form.notes || null,
      };
      return editing ? api.loans.update(editing.id, body) : api.loans.create(body);
    },
    onSuccess: () => {
      setFormOpen(false);
      setEditing(null);
      setForm(emptyForm());
      invalidate();
    },
    onError: (err) => setFormError(err instanceof Error ? err.message : "Could not save this loan."),
  });

  const paymentMutation = useMutation({
    mutationFn: async () => {
      if (!paying) throw new Error("No loan selected.");
      return api.loans.addPayment(paying.id, {
        amount: payment.amount,
        paid_on: payment.paid_on || null,
        principal_amount: payment.principal || null,
        interest_amount: payment.interest || null,
        fee_amount: payment.fee || null,
        confirm: true,
      });
    },
    onSuccess: () => {
      setPaying(null);
      setPayment({ amount: "", paid_on: todayISO(), principal: "", interest: "", fee: "" });
      invalidate();
    },
    onError: (err) =>
      setPaymentError(err instanceof Error ? err.message : "Could not record the repayment."),
  });

  const acceptMutation = useMutation({
    mutationFn: ({ loanId, transactionId }: { loanId: string; transactionId: string }) =>
      api.loans.acceptSuggestion(loanId, transactionId),
    onSuccess: invalidate,
    onError: (err) => setActionError(err instanceof Error ? err.message : "Could not link that payment."),
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => api.loans.remove(id),
    onSuccess: () => {
      setDeleting(null);
      invalidate();
    },
    onError: (err) => {
      setDeleting(null);
      setActionError(err instanceof Error ? err.message : "Could not delete this loan.");
    },
  });

  const openCreate = () => {
    setEditing(null);
    setForm(emptyForm());
    setFormError(null);
    setFormOpen(true);
  };

  const openEdit = (loan: Loan) => {
    setEditing(loan);
    setForm({
      name: loan.name,
      lender: loan.lender ?? "",
      loan_type: loan.loan_type,
      original_amount: loan.original_amount,
      opening_balance: loan.opening_balance,
      balance_as_of: loan.balance_as_of,
      apr: loan.apr ?? "",
      next_payment_date: loan.next_payment_date ?? "",
      scheduled_payment: loan.scheduled_payment ?? "",
      payment_frequency: loan.payment_frequency ?? "monthly",
      remaining_payments: loan.remaining_payments != null ? String(loan.remaining_payments) : "",
      notes: loan.notes ?? "",
    });
    setFormError(null);
    setFormOpen(true);
  };

  const submit = (event: FormEvent) => {
    event.preventDefault();
    setFormError(null);
    saveMutation.mutate();
  };

  if (loansQuery.isLoading) return <LoadingBlock label="Loading loans and advances" />;
  if (loansQuery.error || !loansQuery.data) {
    return (
      <ErrorBanner
        message={
          loansQuery.error instanceof Error ? loansQuery.error.message : "Could not load loans."
        }
        onRetry={() => void loansQuery.refetch()}
      />
    );
  }

  const data = loansQuery.data;

  return (
    <div className="page-stack">
      <PageHeader
        eyebrow="Loans & advances"
        title="What you borrowed, and what is left"
        description="Every liability you track yourself: payday advances, BNPL instalments, credit agreements. Balances are reduced only by repayments you confirm, and any figure derived from incomplete terms is labelled an estimate."
        actions={<Button onClick={openCreate}>Add a loan</Button>}
      />

      {actionError ? <ErrorBanner message={actionError} onRetry={() => setActionError(null)} /> : null}

      <div className="grid grid--three">
        <Card>
          <div className="stat">
            <span className="stat__label">Outstanding</span>
            <span className="stat__value amount--negative">{formatMoney(data.total_outstanding)}</span>
            <span className="stat__hint">{data.active_loans} active</span>
          </div>
        </Card>
        <Card>
          <div className="stat">
            <span className="stat__label">Originally borrowed</span>
            <span className="stat__value">{formatMoney(data.total_original)}</span>
            <span className="stat__hint">Across every loan on record</span>
          </div>
        </Card>
        <Card>
          <div className="stat">
            <span className="stat__label">Next payment</span>
            <span className="stat__value">
              {data.next_payment_date ? formatMoney(data.next_payment_total) : "—"}
            </span>
            <span className="stat__hint">
              {data.next_payment_date ? formatDate(data.next_payment_date) : "No schedule set"}
            </span>
          </div>
        </Card>
      </div>

      {data.loans.length === 0 ? (
        <Card>
          <EmptyState
            title="No loans recorded"
            description="Add a payday advance, a BNPL plan or a personal loan. Its scheduled payment becomes part of Safe-to-Spend, so you cannot spend money that is already promised."
            action={<Button onClick={openCreate}>Add your first loan</Button>}
          />
        </Card>
      ) : (
        <div className="grid grid--two">
          {data.loans.map((loan) => (
            <Card key={loan.id}>
              <div className="card__title">
                <div>
                  <h2 style={{ fontSize: "1.05rem" }}>{loan.name}</h2>
                  <p className="small muted">
                    {LOAN_TYPES.find((t) => t.value === loan.loan_type)?.label ?? loan.loan_type}
                    {loan.lender ? ` · ${loan.lender}` : ""}
                  </p>
                </div>
                <div style={{ display: "flex", gap: "0.3rem", flexWrap: "wrap" }}>
                  <Badge tone={loan.status === "active" ? "warning" : "positive"}>
                    {loan.status === "active" ? "Active" : loan.status === "paid_off" ? "Paid off" : loan.status}
                  </Badge>
                  {loan.balance_is_estimate ? <Badge tone="neutral">Estimate</Badge> : null}
                </div>
              </div>

              <p className={`sts-amount ${Number(loan.current_balance) > 0 ? "amount--negative" : ""}`} style={{ fontSize: "2rem" }}>
                {formatMoney(loan.current_balance)}
              </p>
              <p className="sts-caption">
                {loan.progress_percent}% of the balance you started with has been repaid.
                {loan.balance_is_estimate
                  ? " Calculated from repayments without a principal/interest split."
                  : " Based on repayments you confirmed."}
              </p>

              <div className="sts-breakdown" style={{ marginTop: "0.6rem", paddingTop: "0.6rem" }}>
                <span>
                  Original <strong>{formatMoney(loan.original_amount)}</strong>
                </span>
                <span>
                  Repaid <strong>{formatMoney(loan.total_repaid)}</strong>
                </span>
                <span>
                  Interest <strong>{formatMoney(loan.interest_paid)}</strong>
                </span>
                <span>
                  Fees <strong>{formatMoney(loan.fees_paid)}</strong>
                </span>
              </div>

              <p className="tiny muted" style={{ marginTop: "0.5rem" }}>
                {loan.next_payment_date
                  ? `Next payment ${formatMoney(loan.scheduled_payment ?? "0")} on ${formatDate(loan.next_payment_date)}`
                  : "No next payment date recorded"}
                {loan.apr ? ` · APR ${formatPercent(loan.apr, 2)}` : ""}
                {loan.estimated_payoff_date
                  ? ` · ${loan.payoff_is_estimate ? "Estimated" : "Scheduled"} payoff ${formatDate(loan.estimated_payoff_date)}`
                  : ""}
              </p>
              {loan.remaining_installments != null ? (
                <p className="tiny muted">
                  {loan.remaining_installments} payment(s) left on the recorded schedule.
                </p>
              ) : null}
              {loan.notes ? <p className="small muted">{loan.notes}</p> : null}

              <div className="form-actions" style={{ justifyContent: "flex-start", marginTop: "0.9rem" }}>
                <Button size="sm" variant="secondary" onClick={() => openEdit(loan)}>
                  Edit
                </Button>
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={() => {
                    setPaying(loan);
                    setPayment({ amount: loan.scheduled_payment ?? "", paid_on: todayISO(), principal: "", interest: "", fee: "" });
                    setPaymentError(null);
                  }}
                >
                  Record repayment
                </Button>
                <Button size="sm" variant="ghost" onClick={() => setMatching(loan)}>
                  Match a transaction
                </Button>
                <Button size="sm" variant="ghost" onClick={() => setDeleting(loan)}>
                  Delete
                </Button>
              </div>
            </Card>
          ))}
        </div>
      )}

      <Card>
        <h2 style={{ fontSize: "1.02rem", marginBottom: "0.5rem" }}>How a balance becomes an estimate</h2>
        <p className="small muted">
          A repayment reduces principal by its principal portion. If you record only a total, the
          whole repayment is treated as principal and the remaining balance is marked as an
          estimate. Nothing here claims to be a lender&apos;s figure: no provider connection is
          required, and none is assumed.
        </p>
      </Card>

      <Modal
        open={formOpen}
        title={editing ? "Edit loan" : "Add a loan or advance"}
        description="Enter what you actually owe today, not what you originally borrowed."
        onClose={() => setFormOpen(false)}
        wide
        footer={
          <>
            <Button variant="ghost" type="button" onClick={() => setFormOpen(false)}>
              Cancel
            </Button>
            <Button type="submit" form="loan-form" loading={saveMutation.isPending}>
              {editing ? "Save changes" : "Add loan"}
            </Button>
          </>
        }
      >
        <form id="loan-form" onSubmit={submit} className="page-stack" style={{ gap: "0.9rem" }}>
          <div className="form-grid">
            <Field label="Loan name" htmlFor="loan-name">
              <Input
                id="loan-name"
                required
                value={form.name}
                onChange={(e) => setForm({ ...form, name: e.target.value })}
                placeholder="Payday advance"
                maxLength={120}
              />
            </Field>
            <Field label="Lender (optional)" htmlFor="loan-lender">
              <Input
                id="loan-lender"
                value={form.lender}
                onChange={(e) => setForm({ ...form, lender: e.target.value })}
                placeholder="Cash App"
                maxLength={120}
              />
            </Field>
            <Field label="Type" htmlFor="loan-type">
              <Select
                id="loan-type"
                value={form.loan_type}
                onChange={(e) => setForm({ ...form, loan_type: e.target.value })}
              >
                {LOAN_TYPES.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </Select>
            </Field>
            <Field label="Originally borrowed" htmlFor="loan-original">
              <Input
                id="loan-original"
                required
                inputMode="decimal"
                value={form.original_amount}
                onChange={(e) => setForm({ ...form, original_amount: e.target.value })}
              />
            </Field>
            <Field label="Outstanding now" htmlFor="loan-outstanding" hint="What you owe today.">
              <Input
                id="loan-outstanding"
                required
                inputMode="decimal"
                value={form.opening_balance}
                onChange={(e) => setForm({ ...form, opening_balance: e.target.value })}
              />
            </Field>
            <Field label="Balance as of" htmlFor="loan-asof">
              <Input
                id="loan-asof"
                type="date"
                value={form.balance_as_of}
                onChange={(e) => setForm({ ...form, balance_as_of: e.target.value })}
              />
            </Field>
            <Field label="APR % (optional)" htmlFor="loan-apr">
              <Input
                id="loan-apr"
                inputMode="decimal"
                value={form.apr}
                onChange={(e) => setForm({ ...form, apr: e.target.value })}
                placeholder="24.99"
              />
            </Field>
            <Field label="Next payment date" htmlFor="loan-next">
              <Input
                id="loan-next"
                type="date"
                value={form.next_payment_date}
                onChange={(e) => setForm({ ...form, next_payment_date: e.target.value })}
              />
            </Field>
            <Field label="Scheduled payment" htmlFor="loan-scheduled">
              <Input
                id="loan-scheduled"
                inputMode="decimal"
                value={form.scheduled_payment}
                onChange={(e) => setForm({ ...form, scheduled_payment: e.target.value })}
                placeholder="100.00"
              />
            </Field>
            <Field label="Payment frequency" htmlFor="loan-frequency">
              <Select
                id="loan-frequency"
                value={form.payment_frequency}
                onChange={(e) => setForm({ ...form, payment_frequency: e.target.value })}
                disabled={!form.scheduled_payment}
              >
                <option value="weekly">Weekly</option>
                <option value="biweekly">Every 2 weeks</option>
                <option value="monthly">Monthly</option>
                <option value="quarterly">Quarterly</option>
                <option value="annual">Yearly</option>
              </Select>
            </Field>
            <Field
              label="Payments remaining (optional)"
              htmlFor="loan-remaining"
              hint="Lets the payoff date be calculated."
            >
              <Input
                id="loan-remaining"
                inputMode="numeric"
                value={form.remaining_payments}
                onChange={(e) => setForm({ ...form, remaining_payments: e.target.value })}
              />
            </Field>
          </div>
          <Field label="Notes (optional)" htmlFor="loan-notes">
            <Textarea
              id="loan-notes"
              value={form.notes}
              onChange={(e) => setForm({ ...form, notes: e.target.value })}
              maxLength={1000}
            />
          </Field>
          {formError ? <div className="form-error" role="alert">{formError}</div> : null}
        </form>
      </Modal>

      <Modal
        open={Boolean(paying)}
        title="Record a repayment"
        description="Split the payment if you know how much went to principal, interest or fees. Leave the split blank and the balance is marked an estimate."
        onClose={() => setPaying(null)}
        footer={
          <>
            <Button variant="ghost" type="button" onClick={() => setPaying(null)}>
              Cancel
            </Button>
            <Button
              type="button"
              loading={paymentMutation.isPending}
              onClick={() => paymentMutation.mutate()}
            >
              Record repayment
            </Button>
          </>
        }
      >
        <div className="form-grid">
          <Field label="Amount paid" htmlFor="pay-amount">
            <Input
              id="pay-amount"
              inputMode="decimal"
              value={payment.amount}
              onChange={(e) => setPayment({ ...payment, amount: e.target.value })}
            />
          </Field>
          <Field label="Date paid" htmlFor="pay-date">
            <Input
              id="pay-date"
              type="date"
              value={payment.paid_on}
              onChange={(e) => setPayment({ ...payment, paid_on: e.target.value })}
            />
          </Field>
          <Field label="Of which principal" htmlFor="pay-principal">
            <Input
              id="pay-principal"
              inputMode="decimal"
              value={payment.principal}
              onChange={(e) => setPayment({ ...payment, principal: e.target.value })}
            />
          </Field>
          <Field label="Of which interest" htmlFor="pay-interest">
            <Input
              id="pay-interest"
              inputMode="decimal"
              value={payment.interest}
              onChange={(e) => setPayment({ ...payment, interest: e.target.value })}
            />
          </Field>
          <Field label="Of which fees" htmlFor="pay-fee">
            <Input
              id="pay-fee"
              inputMode="decimal"
              value={payment.fee}
              onChange={(e) => setPayment({ ...payment, fee: e.target.value })}
            />
          </Field>
        </div>
        {paymentError ? <div className="form-error">{paymentError}</div> : null}
      </Modal>

      <Modal
        open={Boolean(matching)}
        title="Match a bank transaction"
        description="Only suggestions with a plausible amount and date are shown. Confirming one reduces the loan balance."
        onClose={() => setMatching(null)}
        footer={
          <Button variant="ghost" type="button" onClick={() => setMatching(null)}>
            Close
          </Button>
        }
      >
        {suggestionsQuery.isLoading ? (
          <LoadingBlock label="Looking for matching debits" />
        ) : (suggestionsQuery.data?.items.length ?? 0) === 0 ? (
          <p className="small muted">
            No unreconciled debit looks like a repayment for this loan. Record the repayment by
            hand if it happened somewhere else.
          </p>
        ) : (
          <div className="page-stack" style={{ gap: "0.6rem" }}>
            {suggestionsQuery.data!.items.map((item) => (
              <div key={item.transaction_id} className="list-row" style={{ alignItems: "center" }}>
                <div style={{ flex: 1 }}>
                  <strong>{item.merchant || item.description}</strong>
                  <div className="tiny muted">
                    {formatMoney(item.amount)} on {formatDate(item.txn_date)} · confidence{" "}
                    {formatPercent(Number(item.confidence) * 100)} {item.is_ambiguous ? "· ambiguous" : ""}
                  </div>
                </div>
                <Button
                  size="sm"
                  loading={acceptMutation.isPending}
                  onClick={() =>
                    matching &&
                    acceptMutation.mutate({ loanId: matching.id, transactionId: item.transaction_id })
                  }
                >
                  Link
                </Button>
              </div>
            ))}
          </div>
        )}
      </Modal>

      <ConfirmDialog
        open={Boolean(deleting)}
        title="Delete this loan?"
        message={
          <>
            <strong>{deleting?.name}</strong> and its repayment history will be removed. The bank
            transactions stay; only the loan record goes.
          </>
        }
        confirmLabel="Delete loan"
        destructive
        busy={deleteMutation.isPending}
        onConfirm={() => deleting && deleteMutation.mutate(deleting.id)}
        onCancel={() => setDeleting(null)}
      />
    </div>
  );
}
