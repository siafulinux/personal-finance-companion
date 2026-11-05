import { useState, type FormEvent } from "react";
import type { Account, Category, Transaction } from "../lib/types";
import { todayISO } from "../lib/format";
import { Button, Field, Input, Select, Textarea } from "./ui";

interface FormState {
  tx_type: string;
  amount: string;
  txn_date: string;
  description: string;
  merchant: string;
  account_id: string;
  transfer_account_id: string;
  category_id: string;
  status: string;
  notes: string;
  tags: string;
}

export function TransactionForm({
  accounts,
  categories,
  initial,
  busy,
  error,
  onSubmit,
  onCancel,
}: {
  accounts: Account[];
  categories: Category[];
  initial?: Transaction;
  busy?: boolean;
  error?: string | null;
  onSubmit: (payload: Record<string, unknown>) => void;
  onCancel: () => void;
}) {
  const [form, setForm] = useState<FormState>(() => ({
    tx_type: initial?.tx_type ?? "purchase",
    amount: initial?.amount ?? "",
    txn_date: initial?.txn_date ?? todayISO(),
    description: initial?.description ?? "",
    merchant: initial?.merchant ?? "",
    account_id: initial?.account_id ?? accounts[0]?.id ?? "",
    transfer_account_id: initial?.transfer_account_id ?? "",
    category_id: initial?.category_id ?? "",
    status: initial?.status ?? "posted",
    notes: initial?.notes ?? "",
    tags: (initial?.tags ?? []).join(", "),
  }));
  const [localError, setLocalError] = useState<string | null>(null);

  const isTransfer = form.tx_type === "transfer";

  const submit = (event: FormEvent) => {
    event.preventDefault();
    setLocalError(null);
    const amount = Number(form.amount);
    if (!form.account_id) return setLocalError("Choose an account.");
    if (!form.description.trim()) return setLocalError("Add a short description.");
    if (!Number.isFinite(amount) || amount <= 0) return setLocalError("Enter an amount above zero.");
    if (isTransfer && (!form.transfer_account_id || form.transfer_account_id === form.account_id)) {
      return setLocalError("A transfer needs two different accounts.");
    }
    const payload: Record<string, unknown> = {
      account_id: form.account_id,
      description: form.description.trim(),
      merchant: form.merchant.trim() || null,
      amount: form.amount,
      tx_type: form.tx_type,
      status: form.status,
      txn_date: form.txn_date,
      category_id: isTransfer ? null : form.category_id || null,
      notes: form.notes.trim() || null,
      tags: form.tags
        .split(",")
        .map((tag) => tag.trim())
        .filter(Boolean)
        .slice(0, 10),
      transfer_account_id: isTransfer ? form.transfer_account_id : null,
    };
    onSubmit(payload);
  };

  const activeAccounts = accounts.filter((account) => !account.is_archived);

  return (
    <form onSubmit={submit} className="page-stack" style={{ gap: "0.9rem" }}>
      <div className="form-grid">
        <Field label="Type" htmlFor="tx-type">
          <Select
            id="tx-type"
            value={form.tx_type}
            onChange={(e) => setForm({ ...form, tx_type: e.target.value })}
          >
            <option value="purchase">Purchase</option>
            <option value="bill_payment">Bill payment</option>
            <option value="income">Income</option>
            <option value="refund">Refund</option>
            <option value="transfer">Internal transfer</option>
          </Select>
        </Field>
        <Field label="Amount" hint="Always a positive amount; the type sets the direction." htmlFor="tx-amount">
          <Input
            id="tx-amount"
            inputMode="decimal"
            required
            value={form.amount}
            onChange={(e) => setForm({ ...form, amount: e.target.value })}
            placeholder="42.50"
          />
        </Field>
        <Field label="Date" htmlFor="tx-date">
          <Input
            id="tx-date"
            type="date"
            required
            max={todayISO()}
            value={form.txn_date}
            onChange={(e) => setForm({ ...form, txn_date: e.target.value })}
          />
        </Field>
        <Field label="Status" htmlFor="tx-status">
          <Select
            id="tx-status"
            value={form.status}
            onChange={(e) => setForm({ ...form, status: e.target.value })}
          >
            <option value="posted">Posted</option>
            <option value="pending">Pending</option>
          </Select>
        </Field>
        <div className="span-2">
          <Field label="Description" htmlFor="tx-description">
            <Input
              id="tx-description"
              required
              maxLength={255}
              value={form.description}
              onChange={(e) => setForm({ ...form, description: e.target.value })}
              placeholder="Groceries at Aldi"
            />
          </Field>
        </div>
        <Field label="Merchant (optional)" htmlFor="tx-merchant">
          <Input
            id="tx-merchant"
            maxLength={160}
            value={form.merchant}
            onChange={(e) => setForm({ ...form, merchant: e.target.value })}
            placeholder="Aldi"
          />
        </Field>
        <Field label="Account" htmlFor="tx-account">
          <Select
            id="tx-account"
            value={form.account_id}
            onChange={(e) => setForm({ ...form, account_id: e.target.value })}
            required
          >
            <option value="">Choose an account</option>
            {activeAccounts.map((account) => (
              <option key={account.id} value={account.id}>
                {account.name}
              </option>
            ))}
          </Select>
        </Field>
        {isTransfer ? (
          <Field label="Transfer to" hint="Transfers never count as income or spending." htmlFor="tx-transfer">
            <Select
              id="tx-transfer"
              value={form.transfer_account_id}
              onChange={(e) => setForm({ ...form, transfer_account_id: e.target.value })}
              required
            >
              <option value="">Choose destination</option>
              {activeAccounts
                .filter((account) => account.id !== form.account_id)
                .map((account) => (
                  <option key={account.id} value={account.id}>
                    {account.name}
                  </option>
                ))}
            </Select>
          </Field>
        ) : (
          <Field label="Category" htmlFor="tx-category">
            <Select
              id="tx-category"
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
        )}
        <div className="span-2">
          <Field label="Tags (comma separated)" htmlFor="tx-tags">
            <Input
              id="tx-tags"
              value={form.tags}
              onChange={(e) => setForm({ ...form, tags: e.target.value })}
              placeholder="work, reimbursable"
            />
          </Field>
        </div>
        <div className="span-2">
          <Field label="Notes (optional)" htmlFor="tx-notes">
            <Textarea
              id="tx-notes"
              value={form.notes}
              onChange={(e) => setForm({ ...form, notes: e.target.value })}
              maxLength={2000}
            />
          </Field>
        </div>
      </div>
      {localError ? <div className="form-error" role="alert">{localError}</div> : null}
      {error ? <div className="form-error" role="alert">{error}</div> : null}
      <div className="form-actions">
        <Button type="button" variant="ghost" onClick={onCancel}>
          Cancel
        </Button>
        <Button type="submit" loading={busy}>
          {initial ? "Save changes" : "Record transaction"}
        </Button>
      </div>
    </form>
  );
}
