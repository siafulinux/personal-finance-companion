import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../lib/api";
import { txTypeLabel, formatDate, formatMoney } from "../lib/format";
import type { Transaction } from "../lib/types";
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
} from "../components/ui";
import { TransactionForm } from "../components/TransactionForm";
import { ImportWizard } from "../components/ImportWizard";

const LIMIT = 25;

export function TransactionsPage() {
  const queryClient = useQueryClient();
  const [search, setSearch] = useState("");
  const [accountId, setAccountId] = useState("");
  const [categoryId, setCategoryId] = useState("");
  const [txType, setTxType] = useState("");
  const [status, setStatus] = useState("");
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");
  const [sort, setSort] = useState("-txn_date");
  const [offset, setOffset] = useState(0);

  const accountsQuery = useQuery({ queryKey: ["accounts", false], queryFn: () => api.accounts.list(false) });
  const categoriesQuery = useQuery({ queryKey: ["categories"], queryFn: () => api.categories.list(false) });
  const importsQuery = useQuery({ queryKey: ["imports"], queryFn: api.imports.list });

  const queryKey = [
    "transactions",
    { search, accountId, categoryId, txType, status, startDate, endDate, sort, offset },
  ];

  const { data, isLoading, error, refetch } = useQuery({
    queryKey,
    queryFn: () =>
      api.transactions.list({
        search: search || undefined,
        account_id: accountId || undefined,
        category_id: categoryId || undefined,
        tx_type: txType || undefined,
        status: status || undefined,
        start_date: startDate || undefined,
        end_date: endDate || undefined,
        sort,
        limit: LIMIT,
        offset,
      }),
  });

  const [formOpen, setFormOpen] = useState(false);
  const [editing, setEditing] = useState<Transaction | null>(null);
  const [formError, setFormError] = useState<string | null>(null);
  const [duplicateWarning, setDuplicateWarning] = useState<string | null>(null);
  const [matchMessage, setMatchMessage] = useState<string | null>(null);
  const [deleting, setDeleting] = useState<Transaction | null>(null);
  const [importOpen, setImportOpen] = useState(false);

  const invalidate = () => {
    void queryClient.invalidateQueries({ queryKey: ["transactions"] });
    void queryClient.invalidateQueries({ queryKey: ["dashboard"] });
    void queryClient.invalidateQueries({ queryKey: ["accounts"] });
    void queryClient.invalidateQueries({ queryKey: ["bills"] });
    void queryClient.invalidateQueries({ queryKey: ["budgets"] });
    void queryClient.invalidateQueries({ queryKey: ["match-suggestions"] });
    void queryClient.invalidateQueries({ queryKey: ["imports"] });
  };

  const createMutation = useMutation({
    mutationFn: (payload: Record<string, unknown>) => api.transactions.create(payload),
    onSuccess: (result) => {
      setFormOpen(false);
      setDuplicateWarning(
        result.possible_duplicates.length
          ? `Possible duplicate: ${result.possible_duplicates[0].description} on ${result.possible_duplicates[0].txn_date} for ${formatMoney(result.possible_duplicates[0].amount)}. You can delete one from the ledger if needed.`
          : null
      );
      setMatchMessage(
        result.match_info?.outcome === "auto"
          ? `Matched to bill: ${result.match_info.bill_name ?? "a bill"} (high confidence).`
          : result.match_info?.outcome === "suggest"
            ? "A possible bill match needs your confirmation under Bills."
            : null
      );
      invalidate();
    },
    onError: (err) => setFormError(err instanceof Error ? err.message : "Unable to save transaction."),
  });

  const updateMutation = useMutation({
    mutationFn: ({ id, payload }: { id: string; payload: Record<string, unknown> }) =>
      api.transactions.update(id, payload),
    onSuccess: () => {
      setEditing(null);
      invalidate();
    },
    onError: (err) => setFormError(err instanceof Error ? err.message : "Unable to update transaction."),
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => api.transactions.remove(id),
    onSuccess: () => {
      setDeleting(null);
      invalidate();
    },
    onError: () => setDeleting(null),
  });

  const resetFilters = () => {
    setSearch("");
    setAccountId("");
    setCategoryId("");
    setTxType("");
    setStatus("");
    setStartDate("");
    setEndDate("");
    setSort("-txn_date");
    setOffset(0);
  };

  const accounts = accountsQuery.data?.accounts ?? [];
  const categories = categoriesQuery.data ?? [];
  const total = data?.total ?? 0;
  const showingFrom = total === 0 ? 0 : offset + 1;
  const showingTo = Math.min(offset + LIMIT, total);

  return (
    <div className="page-stack">
      <PageHeader
        eyebrow="Ledger"
        title="Transactions"
        description="Every balance change lives here. Transfers are excluded from income and spending; refunds reduce the category they came from."
        actions={
          <>
            <Button variant="secondary" onClick={() => setImportOpen(true)}>
              Import CSV
            </Button>
            <Button
              onClick={() => {
                setEditing(null);
                setFormError(null);
                setFormOpen(true);
              }}
              disabled={!accounts.length}
            >
              Add transaction
            </Button>
          </>
        }
      />

      {!accounts.length ? (
        <Card>
          <EmptyState
            title="Add an account first"
            description="Transactions need an account to live in. Create one, then come back here."
          />
        </Card>
      ) : null}

      <Card>
        <div className="filter-bar">
          <div className="field filter-bar__search">
            <label className="field__label" htmlFor="tx-search">
              Search
            </label>
            <Input
              id="tx-search"
              value={search}
              onChange={(e) => {
                setSearch(e.target.value);
                setOffset(0);
              }}
              placeholder="Description, merchant or note"
            />
          </div>
          <Field label="Account" htmlFor="filter-account">
            <Select
              id="filter-account"
              value={accountId}
              onChange={(e) => {
                setAccountId(e.target.value);
                setOffset(0);
              }}
            >
              <option value="">All accounts</option>
              {accounts.map((account) => (
                <option key={account.id} value={account.id}>
                  {account.name}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="Category" htmlFor="filter-category">
            <Select
              id="filter-category"
              value={categoryId}
              onChange={(e) => {
                setCategoryId(e.target.value);
                setOffset(0);
              }}
            >
              <option value="">All categories</option>
              {categories.map((category) => (
                <option key={category.id} value={category.id}>
                  {category.name}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="Type" htmlFor="filter-type">
            <Select
              id="filter-type"
              value={txType}
              onChange={(e) => {
                setTxType(e.target.value);
                setOffset(0);
              }}
            >
              <option value="">All types</option>
              <option value="purchase">Purchase</option>
              <option value="bill_payment">Bill payment</option>
              <option value="income">Income</option>
              <option value="refund">Refund</option>
              <option value="transfer">Transfer</option>
            </Select>
          </Field>
          <Field label="Status" htmlFor="filter-status">
            <Select
              id="filter-status"
              value={status}
              onChange={(e) => {
                setStatus(e.target.value);
                setOffset(0);
              }}
            >
              <option value="">Any status</option>
              <option value="posted">Posted</option>
              <option value="pending">Pending</option>
            </Select>
          </Field>
          <Field label="From" htmlFor="filter-start">
            <Input
              id="filter-start"
              type="date"
              value={startDate}
              onChange={(e) => {
                setStartDate(e.target.value);
                setOffset(0);
              }}
            />
          </Field>
          <Field label="To" htmlFor="filter-end">
            <Input
              id="filter-end"
              type="date"
              value={endDate}
              onChange={(e) => {
                setEndDate(e.target.value);
                setOffset(0);
              }}
            />
          </Field>
          <Field label="Sort" htmlFor="filter-sort">
            <Select id="filter-sort" value={sort} onChange={(e) => setSort(e.target.value)}>
              <option value="-txn_date">Newest first</option>
              <option value="txn_date">Oldest first</option>
              <option value="-amount">Largest amount</option>
              <option value="amount">Smallest amount</option>
              <option value="description">Description A-Z</option>
            </Select>
          </Field>
          <Button variant="ghost" size="sm" onClick={resetFilters} type="button">
            Reset
          </Button>
        </div>
      </Card>

      {duplicateWarning ? (
        <div className="badge badge--warning" style={{ padding: "0.6rem 0.8rem", display: "flex" }}>
          {duplicateWarning}
        </div>
      ) : null}
      {matchMessage ? (
        <div className="badge badge--info" style={{ padding: "0.6rem 0.8rem", display: "flex" }}>
          {matchMessage}
        </div>
      ) : null}

      {error ? (
        <ErrorBanner
          message={error instanceof Error ? error.message : "Unable to load transactions."}
          onRetry={() => void refetch()}
        />
      ) : null}

      <Card className="card--flush">
        {isLoading ? (
          <div style={{ padding: "1.2rem" }}>
            <LoadingBlock label="Loading ledger" />
          </div>
        ) : data && data.items.length ? (
          <>
            <div className="summary-strip" style={{ margin: "0.8rem 1rem 0" }}>
              <span>
                Income <strong>{formatMoney(data.totals.income)}</strong>
              </span>
              <span>
                Spending <strong>{formatMoney(data.totals.spending)}</strong>
              </span>
              <span>
                Transfers <strong>{formatMoney(data.totals.transfers)}</strong>
              </span>
              <span>
                Refunds <strong>{formatMoney(data.totals.refunds)}</strong>
              </span>
              <span>
                Matching rows <strong>{data.total}</strong>
              </span>
            </div>
            <div className="table-wrap">
              <table className="data">
                <thead>
                  <tr>
                    <th>Description</th>
                    <th>Account</th>
                    <th>Type</th>
                    <th>Date</th>
                    <th className="is-right">Amount</th>
                    <th className="is-right">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {data.items.map((txn) => (
                    <tr key={txn.id}>
                      <td>
                        <div className="cell-title">
                          <strong>{txn.description}</strong>
                          <span>
                            {txn.merchant ? `${txn.merchant} · ` : ""}
                            {txn.category_name ?? "Uncategorized"}
                            {txn.source === "csv" ? " · imported" : ""}
                            {txn.tags.length ? ` · ${txn.tags.join(", ")}` : ""}
                          </span>
                        </div>
                      </td>
                      <td>
                        <div className="cell-title">
                          <strong style={{ fontWeight: 500 }}>{txn.account_name}</strong>
                          {txn.transfer_account_name ? (
                            <span>→ {txn.transfer_account_name}</span>
                          ) : null}
                        </div>
                      </td>
                      <td>
                        <Badge
                          tone={
                            txn.status === "pending"
                              ? "warning"
                              : txn.tx_type === "transfer"
                                ? "neutral"
                                : txn.tx_type === "income" || txn.tx_type === "refund"
                                  ? "positive"
                                  : "neutral"
                          }
                        >
                          {txn.status === "pending" ? "Pending" : txTypeLabel(txn.tx_type)}
                        </Badge>
                      </td>
                      <td className="mono tiny">{formatDate(txn.txn_date)}</td>
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
                      <td>
                        <div className="row-actions">
                          <Button
                            size="sm"
                            variant="ghost"
                            onClick={() => {
                              setEditing(txn);
                              setFormError(null);
                            }}
                          >
                            Edit
                          </Button>
                          <Button size="sm" variant="ghost" onClick={() => setDeleting(txn)}>
                            Delete
                          </Button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="pagination" style={{ padding: "0.8rem 1rem" }}>
              <span>
                Showing {showingFrom}-{showingTo} of {total}
              </span>
              <div style={{ display: "flex", gap: "0.4rem" }}>
                <Button
                  size="sm"
                  variant="secondary"
                  disabled={offset === 0}
                  onClick={() => setOffset(Math.max(0, offset - LIMIT))}
                >
                  Previous
                </Button>
                <Button
                  size="sm"
                  variant="secondary"
                  disabled={offset + LIMIT >= total}
                  onClick={() => setOffset(offset + LIMIT)}
                >
                  Next
                </Button>
              </div>
            </div>
          </>
        ) : (
          <EmptyState
            title="No transactions match"
            description="Adjust the filters, add a transaction manually, or import a CSV from your bank."
            action={
              <Button
                onClick={() => {
                  setEditing(null);
                  setFormOpen(true);
                }}
                disabled={!accounts.length}
              >
                Add transaction
              </Button>
            }
          />
        )}
      </Card>

      <Modal
        open={formOpen || Boolean(editing)}
        title={editing ? "Edit transaction" : "Record a transaction"}
        description={
          editing
            ? "Changing amount, date, account or merchant re-checks bill matches."
            : "Manually entered transactions are the source of truth for your balances."
        }
        onClose={() => {
          setFormOpen(false);
          setEditing(null);
        }}
        wide
      >
        <TransactionForm
          key={editing?.id ?? "new"}
          accounts={accounts}
          categories={categories}
          initial={editing ?? undefined}
          busy={createMutation.isPending || updateMutation.isPending}
          error={formError}
          onCancel={() => {
            setFormOpen(false);
            setEditing(null);
          }}
          onSubmit={(payload) => {
            setFormError(null);
            if (editing) {
              updateMutation.mutate({ id: editing.id, payload });
            } else {
              createMutation.mutate(payload);
            }
          }}
        />
      </Modal>

      <Modal
        open={importOpen}
        title="Import transactions from CSV"
        description="Preview first. Duplicates are skipped, invalid rows are reported, and imports can be retried safely."
        onClose={() => setImportOpen(false)}
        wide
      >
        <ImportWizard
          accounts={accounts}
          history={importsQuery.data ?? []}
          onClose={() => {
            setImportOpen(false);
            void queryClient.invalidateQueries({ queryKey: ["imports"] });
          }}
          onImported={invalidate}
        />
      </Modal>

      <ConfirmDialog
        open={Boolean(deleting)}
        title="Delete this transaction?"
        message={
          <>
            <strong>{deleting?.description}</strong> for {formatMoney(deleting?.amount ?? "0")} will
            be removed and balances recalculated. Any confirmed bill match is released.
          </>
        }
        confirmLabel="Delete transaction"
        destructive
        busy={deleteMutation.isPending}
        onConfirm={() => deleting && deleteMutation.mutate(deleting.id)}
        onCancel={() => setDeleting(null)}
      />
    </div>
  );
}
