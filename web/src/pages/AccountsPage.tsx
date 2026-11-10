import { useState, type FormEvent } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useAuth } from "../context/AuthContext";
import { api } from "../lib/api";
import { accountTypeLabel, formatDate, formatMoney, todayISO } from "../lib/format";
import type { Account } from "../lib/types";
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

interface AccountForm {
  name: string;
  account_type: string;
  opening_balance: string;
  opening_balance_date: string;
  credit_limit: string;
  minimum_payment: string;
  description: string;
  include_in_safe_to_spend: boolean;
}

const emptyForm = (): AccountForm => ({
  name: "",
  account_type: "checking",
  opening_balance: "0.00",
  opening_balance_date: todayISO(),
  credit_limit: "",
  minimum_payment: "",
  description: "",
  include_in_safe_to_spend: true,
});

export function AccountsPage() {
  const { profile } = useAuth();
  const queryClient = useQueryClient();
  const [includeArchived, setIncludeArchived] = useState(false);
  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ["accounts", includeArchived],
    queryFn: () => api.accounts.list(includeArchived),
  });

  const [formOpen, setFormOpen] = useState(false);
  const [editing, setEditing] = useState<Account | null>(null);
  const [form, setForm] = useState<AccountForm>(emptyForm());
  const [formError, setFormError] = useState<string | null>(null);
  const [adjusting, setAdjusting] = useState<Account | null>(null);
  const [adjustTarget, setAdjustTarget] = useState("");
  const [adjustReason, setAdjustReason] = useState("");
  const [adjustError, setAdjustError] = useState<string | null>(null);
  const [deleting, setDeleting] = useState<Account | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  const invalidate = () => {
    void queryClient.invalidateQueries({ queryKey: ["accounts"] });
    void queryClient.invalidateQueries({ queryKey: ["dashboard"] });
    void queryClient.invalidateQueries({ queryKey: ["safe-to-spend"] });
  };

  const saveMutation = useMutation({
    mutationFn: async (payload: AccountForm) => {
      if (editing) {
        return api.accounts.update(editing.id, {
          name: payload.name,
          account_type: payload.account_type,
          credit_limit: payload.credit_limit ? payload.credit_limit : null,
          minimum_payment: payload.minimum_payment ? payload.minimum_payment : null,
          description: payload.description || null,
          include_in_safe_to_spend:
            payload.account_type === "credit_card" ? false : payload.include_in_safe_to_spend,
        });
      }
      return api.accounts.create({
        name: payload.name,
        account_type: payload.account_type,
        opening_balance: payload.opening_balance || "0.00",
        opening_balance_date: payload.opening_balance_date,
        currency: "USD",
        credit_limit: payload.credit_limit ? payload.credit_limit : null,
        minimum_payment: payload.minimum_payment ? payload.minimum_payment : null,
        description: payload.description || null,
        include_in_safe_to_spend:
          payload.account_type === "credit_card" ? false : payload.include_in_safe_to_spend,
      });
    },
    onSuccess: () => {
      setFormOpen(false);
      setEditing(null);
      setForm(emptyForm());
      invalidate();
    },
    onError: (err) => setFormError(err instanceof Error ? err.message : "Unable to save account."),
  });

  const adjustMutation = useMutation({
    mutationFn: async () => {
      if (!adjusting) throw new Error("No account selected.");
      return api.accounts.adjust(adjusting.id, {
        target_balance: adjustTarget,
        reason: adjustReason,
      });
    },
    onSuccess: () => {
      setAdjusting(null);
      setAdjustTarget("");
      setAdjustReason("");
      invalidate();
    },
    onError: (err) => setAdjustError(err instanceof Error ? err.message : "Unable to adjust balance."),
  });

  const archiveMutation = useMutation({
    mutationFn: (id: string) => api.accounts.archive(id),
    onSuccess: invalidate,
    onError: (err) => setActionError(err instanceof Error ? err.message : "Unable to archive account."),
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => api.accounts.remove(id),
    onSuccess: () => {
      setDeleting(null);
      invalidate();
    },
    onError: (err) => {
      setDeleting(null);
      setActionError(err instanceof Error ? err.message : "Unable to delete account.");
    },
  });

  const openCreate = () => {
    setEditing(null);
    setForm(emptyForm());
    setFormError(null);
    setFormOpen(true);
  };

  const openEdit = (account: Account) => {
    setEditing(account);
    setForm({
      name: account.name,
      account_type: account.account_type,
      opening_balance: account.opening_balance,
      opening_balance_date: account.opening_balance_date,
      credit_limit: account.credit_limit ?? "",
      minimum_payment: account.minimum_payment ?? "",
      description: account.description ?? "",
      include_in_safe_to_spend: account.include_in_safe_to_spend,
    });
    setFormError(null);
    setFormOpen(true);
  };

  const submit = (event: FormEvent) => {
    event.preventDefault();
    setFormError(null);
    saveMutation.mutate(form);
  };

  if (isLoading) return <LoadingBlock label="Loading accounts" />;
  if (error || !data) {
    return (
      <ErrorBanner
        message={error instanceof Error ? error.message : "Unable to load accounts."}
        onRetry={() => void refetch()}
      />
    );
  }

  return (
    <div className="page-stack">
      <PageHeader
        eyebrow="Accounts"
        title="Where your money actually sits"
        description="Balances are derived from opening balances and posted transactions. Credit limits never count as cash; correct mistakes with an audited adjustment."
        actions={
          <>
            <label className="checkbox" style={{ alignSelf: "center" }}>
              <input
                type="checkbox"
                checked={includeArchived}
                onChange={(e) => setIncludeArchived(e.target.checked)}
              />
              Show archived
            </label>
            <Button onClick={openCreate}>Add account</Button>
          </>
        }
      />

      {actionError ? <ErrorBanner message={actionError} /> : null}

      <div className="grid grid--three">
        <Card>
          <div className="stat">
            <span className="stat__label">Cash</span>
            <span className="stat__value">{formatMoney(data.total_cash)}</span>
            <span className="stat__hint">Eligible and non-eligible cash accounts</span>
          </div>
        </Card>
        <Card>
          <div className="stat">
            <span className="stat__label">Credit debt</span>
            <span className="stat__value amount--negative">{formatMoney(data.total_debt)}</span>
            <span className="stat__hint">Never part of Safe-to-Spend</span>
          </div>
        </Card>
        <Card>
          <div className="stat">
            <span className="stat__label">Net worth</span>
            <span className="stat__value">{formatMoney(data.net_worth)}</span>
            <span className="stat__hint">Cash minus tracked card debt</span>
          </div>
        </Card>
      </div>

      {data.accounts.length ? (
        <div className="grid grid--two">
          {data.accounts.map((account) => (
            <Card key={account.id}>
              <div className="card__title">
                <div>
                  <h2 style={{ fontSize: "1.05rem" }}>{account.name}</h2>
                  <p className="small muted">
                    {accountTypeLabel(account.account_type)}
                    {account.institution ? ` · ${account.institution}` : ""}
                    {account.is_archived ? " · archived" : ""}
                  </p>
                </div>
                <div style={{ display: "flex", gap: "0.3rem", flexWrap: "wrap" }}>
                  {account.include_in_safe_to_spend ? (
                    <Badge tone="positive">Counts toward spending</Badge>
                  ) : account.account_type === "credit_card" ? (
                    <Badge tone="warning">Liability</Badge>
                  ) : (
                    <Badge>Excluded</Badge>
                  )}
                </div>
              </div>

              <p className={`sts-amount ${Number(account.balance) < 0 ? "amount--negative" : ""}`} style={{ fontSize: "2rem" }}>
                {formatMoney(account.balance)}
              </p>

              <div className="sts-breakdown" style={{ marginTop: "0.6rem", paddingTop: "0.6rem" }}>
                <span>
                  Pending <strong>{formatMoney(account.pending_balance)}</strong>
                </span>
                <span>
                  Inflows <strong>{formatMoney(account.total_inflows)}</strong>
                </span>
                <span>
                  Outflows <strong>{formatMoney(account.total_outflows)}</strong>
                </span>
                <span>
                  Transactions <strong>{account.transaction_count}</strong>
                </span>
              </div>

              <p className="tiny muted" style={{ marginTop: "0.5rem" }}>
                Opened {formatDate(account.opening_balance_date)} with{" "}
                {formatMoney(account.opening_balance)}
                {account.credit_limit ? ` · limit ${formatMoney(account.credit_limit)}` : ""}
              </p>
              {account.description ? <p className="small muted">{account.description}</p> : null}

              <div className="form-actions" style={{ justifyContent: "flex-start", marginTop: "0.9rem" }}>
                <Button size="sm" variant="secondary" onClick={() => openEdit(account)}>
                  Edit
                </Button>
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={() => {
                    setAdjusting(account);
                    setAdjustTarget(account.balance);
                    setAdjustReason("");
                    setAdjustError(null);
                  }}
                >
                  Adjust balance
                </Button>
                {!account.is_archived ? (
                  <Button
                    size="sm"
                    variant="ghost"
                    onClick={() => archiveMutation.mutate(account.id)}
                    loading={archiveMutation.isPending}
                  >
                    Archive
                  </Button>
                ) : null}
                <Button size="sm" variant="ghost" onClick={() => setDeleting(account)}>
                  Delete
                </Button>
              </div>
              <p className="tiny muted" style={{ marginTop: "0.5rem" }}>
                Manually maintained. Reconcile against your institution when it differs.
              </p>
            </Card>
          ))}
        </div>
      ) : (
        <Card>
          <EmptyState
            title="No accounts yet"
            description="Add your checking, savings, cash or credit accounts. Safe-to-Spend starts with the cash accounts you mark as contributing."
            action={<Button onClick={openCreate}>Add your first account</Button>}
          />
        </Card>
      )}

      <p className="tiny muted">
        Signed in as {profile?.user.email}. Opening balances are immutable after creation; use a
        balance adjustment to preserve an audit trail.
      </p>

      <Modal
        open={formOpen}
        title={editing ? "Edit account" : "Add an account"}
        description={
          editing
            ? "Opening balances cannot be edited. Use a balance adjustment instead."
            : "Start from a real balance you can verify in your banking app."
        }
        onClose={() => setFormOpen(false)}
        footer={
          <>
            <Button variant="ghost" type="button" onClick={() => setFormOpen(false)}>
              Cancel
            </Button>
            <Button type="submit" form="account-form" loading={saveMutation.isPending}>
              {editing ? "Save changes" : "Create account"}
            </Button>
          </>
        }
      >
        <form id="account-form" onSubmit={submit} className="page-stack" style={{ gap: "0.9rem" }}>
          <div className="form-grid">
            <Field label="Account name" htmlFor="acct-name">
              <Input
                id="acct-name"
                required
                value={form.name}
                onChange={(e) => setForm({ ...form, name: e.target.value })}
                placeholder="Everyday checking"
                maxLength={120}
              />
            </Field>
            <Field label="Account type" htmlFor="acct-type">
              <Select
                id="acct-type"
                value={form.account_type}
                onChange={(e) =>
                  setForm({
                    ...form,
                    account_type: e.target.value,
                    include_in_safe_to_spend:
                      e.target.value === "credit_card" ? false : form.include_in_safe_to_spend,
                  })
                }
              >
                <option value="checking">Checking</option>
                <option value="savings">Savings</option>
                <option value="cash">Cash</option>
                <option value="digital_wallet">Digital wallet</option>
                <option value="payment_app">Payment app / Cash App</option>
                <option value="credit_card">Credit card</option>
                <option value="other">Other</option>
              </Select>
            </Field>
            {!editing ? (
              <>
                <Field label="Opening balance" htmlFor="acct-balance">
                  <Input
                    id="acct-balance"
                    inputMode="decimal"
                    value={form.opening_balance}
                    onChange={(e) => setForm({ ...form, opening_balance: e.target.value })}
                  />
                </Field>
                <Field label="Opening balance date" htmlFor="acct-date">
                  <Input
                    id="acct-date"
                    type="date"
                    value={form.opening_balance_date}
                    onChange={(e) => setForm({ ...form, opening_balance_date: e.target.value })}
                  />
                </Field>
              </>
            ) : null}
            {form.account_type === "credit_card" ? (
              <>
                <Field
                  label="Credit limit (reference only)"
                  hint="Limits are never treated as available cash."
                  htmlFor="acct-limit"
                >
                  <Input
                    id="acct-limit"
                    inputMode="decimal"
                    value={form.credit_limit}
                    onChange={(e) => setForm({ ...form, credit_limit: e.target.value })}
                  />
                </Field>
                <Field
                  label="Minimum payment (optional)"
                  hint="Reserved in Safe-to-Spend and shown in Obligations. Never guessed from the balance."
                  htmlFor="acct-minimum"
                >
                  <Input
                    id="acct-minimum"
                    inputMode="decimal"
                    value={form.minimum_payment}
                    onChange={(e) => setForm({ ...form, minimum_payment: e.target.value })}
                    placeholder="35.00"
                  />
                </Field>
              </>
            ) : null}
          </div>
          <Field label="Notes (optional)" htmlFor="acct-desc">
            <Textarea
              id="acct-desc"
              value={form.description}
              onChange={(e) => setForm({ ...form, description: e.target.value })}
              maxLength={1000}
            />
          </Field>
          {form.account_type !== "credit_card" ? (
            <label className="checkbox">
              <input
                type="checkbox"
                checked={form.include_in_safe_to_spend}
                onChange={(e) =>
                  setForm({ ...form, include_in_safe_to_spend: e.target.checked })
                }
              />
              Include this account in Safe-to-Spend and spending money
            </label>
          ) : (
            <p className="tiny muted">
              Credit cards are liabilities. Their balances reduce net worth but never add to
              Safe-to-Spend.
            </p>
          )}
          {formError ? <div className="form-error" role="alert">{formError}</div> : null}
        </form>
      </Modal>

      <Modal
        open={Boolean(adjusting)}
        title="Adjust account balance"
        description="Use this to reconcile with the real institution. The change is logged with before/after balances."
        onClose={() => setAdjusting(null)}
        footer={
          <>
            <Button variant="ghost" type="button" onClick={() => setAdjusting(null)}>
              Cancel
            </Button>
            <Button
              type="button"
              loading={adjustMutation.isPending}
              onClick={() => adjustMutation.mutate()}
            >
              Record adjustment
            </Button>
          </>
        }
      >
        <p className="small muted">
          {adjusting?.name} currently shows {formatMoney(adjusting?.balance ?? "0")}.
        </p>
        <Field label="Real balance" htmlFor="adjust-target">
          <Input
            id="adjust-target"
            inputMode="decimal"
            value={adjustTarget}
            onChange={(e) => setAdjustTarget(e.target.value)}
          />
        </Field>
        <Field label="Reason" hint="For example: matched the bank statement on 12 Nov." htmlFor="adjust-reason">
          <Input
            id="adjust-reason"
            value={adjustReason}
            onChange={(e) => setAdjustReason(e.target.value)}
            maxLength={255}
            placeholder="Matched bank statement"
          />
        </Field>
        {adjustError ? <div className="form-error">{adjustError}</div> : null}
      </Modal>

      <ConfirmDialog
        open={Boolean(deleting)}
        title="Delete this account?"
        message={
          <>
            <strong>{deleting?.name}</strong> will be removed. Accounts with any transaction
            history cannot be deleted; archive them instead so reports stay accurate.
          </>
        }
        confirmLabel="Delete account"
        destructive
        busy={deleteMutation.isPending}
        onConfirm={() => deleting && deleteMutation.mutate(deleting.id)}
        onCancel={() => setDeleting(null)}
      />
    </div>
  );
}
