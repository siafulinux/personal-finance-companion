import { useState, type FormEvent } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../lib/api";
import { formatDate, formatMoney, todayISO } from "../lib/format";
import type { SavingsGoal, SavingsMode } from "../lib/types";
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
  ProgressBar,
  Select,
  Textarea,
} from "../components/ui";

interface GoalForm {
  name: string;
  target_amount: string;
  target_date: string;
  mode: SavingsMode;
  saved_amount: string;
  account_id: string;
  contribution_amount: string;
  contribution_frequency: string;
  notes: string;
}

const emptyForm = (): GoalForm => ({
  name: "",
  target_amount: "",
  target_date: "",
  mode: "virtual",
  saved_amount: "0.00",
  account_id: "",
  contribution_amount: "",
  contribution_frequency: "monthly",
  notes: "",
});

export function SavingsPage() {
  const queryClient = useQueryClient();
  const [formOpen, setFormOpen] = useState(false);
  const [editing, setEditing] = useState<SavingsGoal | null>(null);
  const [form, setForm] = useState<GoalForm>(emptyForm());
  const [formError, setFormError] = useState<string | null>(null);
  const [contributing, setContributing] = useState<SavingsGoal | null>(null);
  const [contribution, setContribution] = useState({ amount: "", contributed_on: todayISO() });
  const [contributionError, setContributionError] = useState<string | null>(null);
  const [deleting, setDeleting] = useState<SavingsGoal | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  const goalsQuery = useQuery({ queryKey: ["savings"], queryFn: api.savings.list });
  const accountsQuery = useQuery({ queryKey: ["accounts", false], queryFn: () => api.accounts.list(false) });

  const invalidate = () => {
    void queryClient.invalidateQueries({ queryKey: ["savings"] });
    void queryClient.invalidateQueries({ queryKey: ["safe-to-spend"] });
    void queryClient.invalidateQueries({ queryKey: ["dashboard"] });
    void queryClient.invalidateQueries({ queryKey: ["obligations"] });
  };

  const saveMutation = useMutation({
    mutationFn: async () => {
      const body = {
        name: form.name,
        target_amount: form.target_amount,
        target_date: form.target_date || null,
        mode: form.mode,
        saved_amount: form.saved_amount || "0.00",
        account_id: form.mode === "account" ? form.account_id : null,
        contribution_amount: form.contribution_amount || null,
        contribution_frequency: form.contribution_amount ? form.contribution_frequency : null,
        notes: form.notes || null,
      };
      return editing ? api.savings.update(editing.id, body) : api.savings.create(body);
    },
    onSuccess: () => {
      setFormOpen(false);
      setEditing(null);
      setForm(emptyForm());
      invalidate();
    },
    onError: (err) => setFormError(err instanceof Error ? err.message : "Could not save this goal."),
  });

  const contributionMutation = useMutation({
    mutationFn: async () => {
      if (!contributing) throw new Error("No goal selected.");
      return api.savings.contribute(contributing.id, {
        amount: contribution.amount,
        contributed_on: contribution.contributed_on,
      });
    },
    onSuccess: () => {
      setContributing(null);
      setContribution({ amount: "", contributed_on: todayISO() });
      invalidate();
    },
    onError: (err) =>
      setContributionError(err instanceof Error ? err.message : "Could not record the contribution."),
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => api.savings.remove(id),
    onSuccess: () => {
      setDeleting(null);
      invalidate();
    },
    onError: (err) => {
      setDeleting(null);
      setActionError(err instanceof Error ? err.message : "Could not delete this goal.");
    },
  });

  const openCreate = () => {
    setEditing(null);
    setForm(emptyForm());
    setFormError(null);
    setFormOpen(true);
  };

  const openEdit = (goal: SavingsGoal) => {
    setEditing(goal);
    setForm({
      name: goal.name,
      target_amount: goal.target_amount,
      target_date: goal.target_date ?? "",
      mode: goal.mode,
      saved_amount: goal.saved_amount,
      account_id: goal.account_id ?? "",
      contribution_amount: goal.contribution_amount ?? "",
      contribution_frequency: goal.contribution_frequency ?? "monthly",
      notes: goal.notes ?? "",
    });
    setFormError(null);
    setFormOpen(true);
  };

  const submit = (event: FormEvent) => {
    event.preventDefault();
    setFormError(null);
    saveMutation.mutate();
  };

  if (goalsQuery.isLoading) return <LoadingBlock label="Loading savings goals" />;
  if (goalsQuery.error || !goalsQuery.data) {
    return (
      <ErrorBanner
        message={goalsQuery.error instanceof Error ? goalsQuery.error.message : "Could not load savings."}
        onRetry={() => void goalsQuery.refetch()}
      />
    );
  }

  const data = goalsQuery.data;
  const accounts = (accountsQuery.data?.accounts ?? []).filter(
    (account) => account.account_type === "savings" || account.account_type === "checking",
  );

  return (
    <div className="page-stack">
      <PageHeader
        eyebrow="Savings goals"
        title="Money set aside, set aside once"
        description="A virtual goal protects money that stays in your spending account. An account-backed goal uses the balance of its own savings account. The engine deducts a dollar at most once, whichever you choose."
        actions={<Button onClick={openCreate}>New goal</Button>}
      />

      {actionError ? <ErrorBanner message={actionError} onRetry={() => setActionError(null)} /> : null}

      <div className="grid grid--three">
        <Card>
          <div className="stat">
            <span className="stat__label">Saved</span>
            <span className="stat__value">{formatMoney(data.total_saved)}</span>
            <span className="stat__hint">of {formatMoney(data.total_target)} across active goals</span>
          </div>
        </Card>
        <Card>
          <div className="stat">
            <span className="stat__label">Protected from spending</span>
            <span className="stat__value">{formatMoney(data.total_protected)}</span>
            <span className="stat__hint">Subtracted from Safe-to-Spend</span>
          </div>
        </Card>
        <Card>
          <div className="stat">
            <span className="stat__label">Planned each month</span>
            <span className="stat__value">{formatMoney(data.monthly_commitment)}</span>
            <span className="stat__hint">Earmarked, never moved automatically</span>
          </div>
        </Card>
      </div>

      {data.goals.length === 0 ? (
        <Card>
          <EmptyState
            title="No savings goals yet"
            description="Emergency fund, holidays, a car, Christmas. Give each one a target and the engine will keep that money out of your spending room."
            action={<Button onClick={openCreate}>Create your first goal</Button>}
          />
        </Card>
      ) : (
        <div className="grid grid--two">
          {data.goals.map((goal) => (
            <Card key={goal.id}>
              <div className="card__title">
                <div>
                  <h2 style={{ fontSize: "1.05rem" }}>{goal.name}</h2>
                  <p className="small muted">
                    {goal.mode === "virtual" ? "Virtual allocation" : `Account: ${goal.account_name ?? "—"}`}
                    {goal.target_date ? ` · target ${formatDate(goal.target_date)}` : ""}
                  </p>
                </div>
                <Badge tone={goal.status === "completed" ? "positive" : "neutral"}>
                  {goal.status === "completed" ? "Complete" : `${goal.progress_percent}%`}
                </Badge>
              </div>

              <p className="sts-amount" style={{ fontSize: "2rem" }}>
                {formatMoney(goal.saved_amount)}
              </p>
              <p className="sts-caption">
                of {formatMoney(goal.target_amount)} · {formatMoney(goal.remaining_to_target)} to go
              </p>
              <div style={{ marginTop: "0.6rem" }}>
                <ProgressBar
                  percent={Number(goal.progress_percent)}
                  tone={goal.status === "completed" ? "accent" : "warning"}
                  label={`${goal.name} progress`}
                />
              </div>

              <div className="sts-breakdown" style={{ marginTop: "0.7rem" }}>
                <span>
                  Protected now <strong>{formatMoney(goal.protected_amount)}</strong>
                </span>
                {goal.contribution_amount ? (
                  <span>
                    Plan <strong>{formatMoney(goal.contribution_amount)} / {goal.contribution_frequency}</strong>
                  </span>
                ) : (
                  <span>
                    Plan <strong>none</strong>
                  </span>
                )}
                {goal.next_contribution_date ? (
                  <span>
                    Next <strong>{formatDate(goal.next_contribution_date)}</strong>
                  </span>
                ) : null}
                {goal.required_per_period ? (
                  <span>
                    Needed <strong>{formatMoney(goal.required_per_period)} / period</strong>
                  </span>
                ) : null}
              </div>

              {goal.mode === "account" && goal.account_is_spendable === false ? (
                <p className="tiny muted" style={{ marginTop: "0.5rem" }}>
                  This goal&apos;s account is excluded from spending, so its balance is already out
                  of Safe-to-Spend and nothing further is deducted.
                </p>
              ) : null}
              {goal.projected_completion ? (
                <p className="tiny muted">
                  At the planned rate it reaches its target around{" "}
                  {formatDate(goal.projected_completion)}.
                </p>
              ) : null}
              {goal.notes ? <p className="small muted">{goal.notes}</p> : null}

              <div className="form-actions" style={{ justifyContent: "flex-start", marginTop: "0.9rem" }}>
                <Button
                  size="sm"
                  variant="secondary"
                  onClick={() => {
                    setContributing(goal);
                    setContribution({ amount: goal.contribution_amount ?? "", contributed_on: todayISO() });
                    setContributionError(null);
                  }}
                >
                  Add money
                </Button>
                <Button size="sm" variant="ghost" onClick={() => openEdit(goal)}>
                  Edit
                </Button>
                <Button size="sm" variant="ghost" onClick={() => setDeleting(goal)}>
                  Delete
                </Button>
              </div>
            </Card>
          ))}
        </div>
      )}

      <Card>
        <h2 style={{ fontSize: "1.02rem", marginBottom: "0.5rem" }}>What this feature will not do</h2>
        <p className="small muted">
          Recording a contribution tells the plan that money is spoken for. It does not move money
          between your accounts, and no transfer is ever initiated on your behalf.
        </p>
      </Card>

      <Modal
        open={formOpen}
        title={editing ? "Edit savings goal" : "New savings goal"}
        onClose={() => setFormOpen(false)}
        wide
        footer={
          <>
            <Button variant="ghost" type="button" onClick={() => setFormOpen(false)}>
              Cancel
            </Button>
            <Button type="submit" form="savings-form" loading={saveMutation.isPending}>
              {editing ? "Save changes" : "Create goal"}
            </Button>
          </>
        }
      >
        <form id="savings-form" onSubmit={submit} className="page-stack" style={{ gap: "0.9rem" }}>
          <div className="form-grid">
            <Field label="Goal name" htmlFor="goal-name">
              <Input
                id="goal-name"
                required
                value={form.name}
                onChange={(e) => setForm({ ...form, name: e.target.value })}
                placeholder="Emergency fund"
                maxLength={120}
              />
            </Field>
            <Field label="Target amount" htmlFor="goal-target">
              <Input
                id="goal-target"
                required
                inputMode="decimal"
                value={form.target_amount}
                onChange={(e) => setForm({ ...form, target_amount: e.target.value })}
              />
            </Field>
            <Field label="Target date (optional)" htmlFor="goal-date">
              <Input
                id="goal-date"
                type="date"
                value={form.target_date}
                onChange={(e) => setForm({ ...form, target_date: e.target.value })}
              />
            </Field>
            <Field label="How the money is held" htmlFor="goal-mode">
              <Select
                id="goal-mode"
                value={form.mode}
                onChange={(e) => setForm({ ...form, mode: e.target.value as SavingsMode })}
              >
                <option value="virtual">Stays in my spending account (protected virtually)</option>
                <option value="account">Sits in its own savings account</option>
              </Select>
            </Field>
            {form.mode === "account" ? (
              <Field label="Savings account" htmlFor="goal-account">
                <Select
                  id="goal-account"
                  required
                  value={form.account_id}
                  onChange={(e) => setForm({ ...form, account_id: e.target.value })}
                >
                  <option value="">Choose an account</option>
                  {accounts.map((account) => (
                    <option key={account.id} value={account.id}>
                      {account.name}
                    </option>
                  ))}
                </Select>
              </Field>
            ) : null}
            <Field label="Already set aside" htmlFor="goal-saved">
              <Input
                id="goal-saved"
                inputMode="decimal"
                value={form.saved_amount}
                onChange={(e) => setForm({ ...form, saved_amount: e.target.value })}
              />
            </Field>
            <Field label="Planned contribution (optional)" htmlFor="goal-contribution">
              <Input
                id="goal-contribution"
                inputMode="decimal"
                value={form.contribution_amount}
                onChange={(e) => setForm({ ...form, contribution_amount: e.target.value })}
                placeholder="25.00"
              />
            </Field>
            <Field label="Contribution frequency" htmlFor="goal-frequency">
              <Select
                id="goal-frequency"
                value={form.contribution_frequency}
                onChange={(e) => setForm({ ...form, contribution_frequency: e.target.value })}
                disabled={!form.contribution_amount}
              >
                <option value="weekly">Weekly</option>
                <option value="biweekly">Every 2 weeks</option>
                <option value="monthly">Monthly</option>
                <option value="quarterly">Quarterly</option>
              </Select>
            </Field>
          </div>
          <Field label="Notes (optional)" htmlFor="goal-notes">
            <Textarea
              id="goal-notes"
              value={form.notes}
              onChange={(e) => setForm({ ...form, notes: e.target.value })}
              maxLength={1000}
            />
          </Field>
          {formError ? <div className="form-error" role="alert">{formError}</div> : null}
        </form>
      </Modal>

      <Modal
        open={Boolean(contributing)}
        title="Add to this goal"
        description="This records an allocation, not a bank transfer."
        onClose={() => setContributing(null)}
        footer={
          <>
            <Button variant="ghost" type="button" onClick={() => setContributing(null)}>
              Cancel
            </Button>
            <Button
              type="button"
              loading={contributionMutation.isPending}
              onClick={() => contributionMutation.mutate()}
            >
              Record contribution
            </Button>
          </>
        }
      >
        <div className="form-grid">
          <Field label="Amount" htmlFor="contribution-amount">
            <Input
              id="contribution-amount"
              inputMode="decimal"
              value={contribution.amount}
              onChange={(e) => setContribution({ ...contribution, amount: e.target.value })}
            />
          </Field>
          <Field label="Date" htmlFor="contribution-date">
            <Input
              id="contribution-date"
              type="date"
              value={contribution.contributed_on}
              onChange={(e) => setContribution({ ...contribution, contributed_on: e.target.value })}
            />
          </Field>
        </div>
        {contributionError ? <div className="form-error">{contributionError}</div> : null}
      </Modal>

      <ConfirmDialog
        open={Boolean(deleting)}
        title="Delete this savings goal?"
        message={
          <>
            <strong>{deleting?.name}</strong> and its contribution history will be removed. No
            money moves: deleting a goal only releases the allocation.
          </>
        }
        confirmLabel="Delete goal"
        destructive
        busy={deleteMutation.isPending}
        onConfirm={() => deleting && deleteMutation.mutate(deleting.id)}
        onCancel={() => setDeleting(null)}
      />
    </div>
  );
}
