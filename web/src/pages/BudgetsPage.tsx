import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ApiError, api } from "../lib/api";
import { formatMoney, formatMonth, formatPercent, monthInputValue, parseMonth } from "../lib/format";
import type { BudgetRow, Category } from "../lib/types";
import {
  Badge,
  Button,
  Card,
  EmptyState,
  ErrorBanner,
  Field,
  Input,
  LoadingBlock,
  Modal,
  PageHeader,
  ProgressBar,
  Select,
} from "../components/ui";

const now = new Date();

export function BudgetsPage() {
  const queryClient = useQueryClient();
  const [monthValue, setMonthValue] = useState(monthInputValue(now.getFullYear(), now.getMonth() + 1));
  const { year, month } = parseMonth(monthValue);

  const categoriesQuery = useQuery({ queryKey: ["categories"], queryFn: () => api.categories.list(false) });
  const budgetQuery = useQuery({
    queryKey: ["budget", year, month],
    queryFn: () => api.budgets.month(year, month),
    retry: false,
  });

  const [editorOpen, setEditorOpen] = useState(false);
  const [wizardOpen, setWizardOpen] = useState(false);
  const [wizardIncome, setWizardIncome] = useState("");
  const [wizardSavings, setWizardSavings] = useState("10");
  const [wizardIncludeBills, setWizardIncludeBills] = useState(true);
  const [priorities, setPriorities] = useState<Record<string, number>>({});
  const [formError, setFormError] = useState<string | null>(null);
  const [allocations, setAllocations] = useState<Record<string, { amount: string; carryover: boolean }>>({});
  const [plannedIncome, setPlannedIncome] = useState("");

  const invalidate = () => {
    void queryClient.invalidateQueries({ queryKey: ["budget"] });
    void queryClient.invalidateQueries({ queryKey: ["dashboard"] });
    void queryClient.invalidateQueries({ queryKey: ["safe-to-spend"] });
    void queryClient.invalidateQueries({ queryKey: ["shopping"] });
  };

  const categories = categoriesQuery.data ?? [];
  const budget = budgetQuery.data;
  const notFound = budgetQuery.error instanceof ApiError && budgetQuery.error.status === 404;

  const createBlank = useMutation({
    mutationFn: () =>
      api.budgets.create({
        year,
        month,
        allocations: [],
        planned_income: plannedIncome || null,
      }),
    onSuccess: () => {
      setWizardOpen(false);
      invalidate();
    },
    onError: (err) => setFormError(err instanceof Error ? err.message : "Unable to create budget."),
  });

  const wizard = useMutation({
    mutationFn: () =>
      api.budgets.wizard({
        year,
        month,
        expected_income: wizardIncome,
        savings_target_percent: wizardSavings || "0",
        include_existing_bills: wizardIncludeBills,
        priorities: Object.entries(priorities)
          .filter(([, weight]) => weight > 0)
          .map(([category_id, weight]) => ({ category_id, weight })),
      }),
    onSuccess: () => {
      setWizardOpen(false);
      invalidate();
    },
    onError: (err) => setFormError(err instanceof Error ? err.message : "Unable to build the budget."),
  });

  const saveAllocations = useMutation({
    mutationFn: async () => {
      if (!budget) throw new Error("No budget to edit.");
      return api.budgets.update(budget.id, {
        planned_income: plannedIncome || null,
        allocations: Object.entries(allocations)
          .filter(([, value]) => Number(value.amount) > 0)
          .map(([category_id, value]) => ({
            category_id,
            amount: value.amount,
            carryover_enabled: value.carryover,
          })),
      });
    },
    onSuccess: () => {
      setEditorOpen(false);
      invalidate();
    },
    onError: (err) => setFormError(err instanceof Error ? err.message : "Unable to save allocations."),
  });

  const copyPrevious = useMutation({
    mutationFn: () => {
      const previous = new Date(year, month - 2, 1);
      return api.budgets.copy({
        source_year: previous.getFullYear(),
        source_month: previous.getMonth() + 1,
        year,
        month,
        adjust_percent: "0",
      });
    },
    onSuccess: invalidate,
    onError: (err) => setFormError(err instanceof Error ? err.message : "Unable to copy the budget."),
  });

  const openEditor = () => {
    if (!budget) return;
    const next: Record<string, { amount: string; carryover: boolean }> = {};
    categories.forEach((category) => {
      const row = budget.rows.find((item) => item.category_id === category.id);
      next[category.id] = {
        amount: row ? row.allocated : "0.00",
        carryover: row?.carryover_enabled ?? false,
      };
    });
    setAllocations(next);
    setPlannedIncome(budget.planned_income ?? "");
    setFormError(null);
    setEditorOpen(true);
  };

  const rowsByCategory = useMemo(() => {
    const map: Record<string, BudgetRow> = {};
    budget?.rows.forEach((row) => {
      map[row.category_id] = row;
    });
    return map;
  }, [budget]);

  return (
    <div className="page-stack">
      <PageHeader
        eyebrow="Budgets"
        title="Give every dollar a job"
        description="Limit what each category can consume. Spending updates automatically from posted transactions; upcoming bills are shown as context, not double-counted."
        actions={
          <>
            <Field label="Month" htmlFor="budget-month">
              <Input
                id="budget-month"
                type="month"
                value={monthValue}
                onChange={(e) => setMonthValue(e.target.value)}
              />
            </Field>
            {budget ? (
              <>
                <Button variant="secondary" onClick={() => copyPrevious.mutate()} loading={copyPrevious.isPending}>
                  Copy prior month
                </Button>
                <Button onClick={openEditor}>Edit budget</Button>
              </>
            ) : (
              <Button
                onClick={() => {
                  setFormError(null);
                  setWizardIncome("");
                  setWizardOpen(true);
                }}
              >
                Build a budget
              </Button>
            )}
          </>
        }
      />

      {formError ? <ErrorBanner message={formError} /> : null}

      {budgetQuery.isLoading ? (
        <LoadingBlock label="Loading budget" />
      ) : notFound ? (
        <Card>
          <EmptyState
            title={`No budget for ${formatMonth(year, month)}`}
            description="Build one from your income, fixed bills and priorities. Nothing here assumes a generic 50/30/20 split."
            action={
              <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap", justifyContent: "center" }}>
                <Button
                  onClick={() => {
                    setFormError(null);
                    setWizardOpen(true);
                  }}
                >
                  Use the setup wizard
                </Button>
                <Button
                  variant="secondary"
                  onClick={() => createBlank.mutate()}
                  loading={createBlank.isPending}
                >
                  Start with an empty budget
                </Button>
              </div>
            }
          />
        </Card>
      ) : budgetQuery.error ? (
        <ErrorBanner
          message={budgetQuery.error instanceof Error ? budgetQuery.error.message : "Unable to load budget."}
          onRetry={() => void budgetQuery.refetch()}
        />
      ) : budget ? (
        <>
          <div className="grid grid--three">
            <Card>
              <div className="stat">
                <span className="stat__label">Planned</span>
                <span className="stat__value">{formatMoney(budget.total_allocated)}</span>
                <span className="stat__hint">
                  {budget.planned_income
                    ? `of ${formatMoney(budget.planned_income)} planned income`
                    : `actual income ${formatMoney(budget.income_this_month)}`}
                </span>
              </div>
            </Card>
            <Card>
              <div className="stat">
                <span className="stat__label">Spent</span>
                <span className="stat__value">{formatMoney(budget.total_spent)}</span>
                <span className="stat__hint">{formatPercent(budget.percent_used)} of plan used</span>
              </div>
              <div style={{ marginTop: "0.7rem" }}>
                <ProgressBar
                  percent={Number(budget.percent_used)}
                  tone={Number(budget.percent_used) > 100 ? "danger" : Number(budget.percent_used) > 80 ? "warning" : "accent"}
                  label="Budget used"
                />
              </div>
            </Card>
            <Card>
              <div className="stat">
                <span className="stat__label">Unallocated</span>
                <span className={`stat__value ${Number(budget.unallocated) < 0 ? "amount--negative" : ""}`}>
                  {formatMoney(budget.unallocated)}
                </span>
                <span className="stat__hint">
                  {Number(budget.unallocated) < 0
                    ? "Allocated more than planned income"
                    : "Still available to assign"}
                </span>
              </div>
            </Card>
          </div>

          {Number(budget.total_remaining) < 0 ? (
            <div className="warning-list">
              <li>
                Overall budget is overspent by {formatMoney(Math.abs(Number(budget.total_remaining)))}.
                Safe-to-Spend still governs what cash exists.
              </li>
            </div>
          ) : null}

          <Card className="card--flush">
            <div className="table-wrap">
              <table className="data">
                <thead>
                  <tr>
                    <th>Category</th>
                    <th className="is-right">Budgeted</th>
                    <th className="is-right">Spent</th>
                    <th className="is-right">Remaining</th>
                    <th>Progress</th>
                    <th className="is-right">Upcoming</th>
                    <th className="is-right">Trend</th>
                  </tr>
                </thead>
                <tbody>
                  {budget.rows.map((row) => {
                    const percent = Number(row.percent_used);
                    const over = Number(row.remaining) < 0;
                    return (
                      <tr key={row.category_id}>
                        <td>
                          <div className="cell-title">
                            <strong>
                              <span className="category-bar__swatch" style={{ background: row.category_color }} />
                              {row.category_name}
                            </strong>
                            <span>
                              {row.transaction_count} transaction{row.transaction_count === 1 ? "" : "s"}
                              {row.carryover_enabled ? " · carryover on" : ""}
                              {Number(row.carryover_in) > 0
                                ? ` · +${formatMoney(row.carryover_in)} carried in`
                                : ""}
                            </span>
                          </div>
                        </td>
                        <td className="is-right mono">{formatMoney(row.allocated)}</td>
                        <td className="is-right mono">{formatMoney(row.spent)}</td>
                        <td className={`is-right mono ${over ? "amount--negative" : ""}`}>
                          {formatMoney(row.remaining)}
                        </td>
                        <td style={{ minWidth: 130 }}>
                          <ProgressBar
                            percent={percent}
                            tone={over ? "danger" : percent > 80 ? "warning" : "accent"}
                            label={`${row.category_name} used`}
                          />
                          <span className="tiny muted">{formatPercent(percent)}</span>
                        </td>
                        <td className="is-right mono tiny">
                          {Number(row.upcoming_commitments) > 0
                            ? formatMoney(row.upcoming_commitments)
                            : "—"}
                        </td>
                        <td className="is-right tiny">
                          {row.trend_percent === null ? (
                            <span className="muted">new</span>
                          ) : (
                            <Badge tone={Number(row.trend_percent) > 0 ? "warning" : "positive"}>
                              {Number(row.trend_percent) > 0 ? "+" : ""}
                              {formatPercent(row.trend_percent)}
                            </Badge>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                  {!budget.rows.length ? (
                    <tr>
                      <td colSpan={7}>
                        <EmptyState
                          title="No allocations yet"
                          description="Edit this budget to assign money to the categories you care about."
                          action={<Button onClick={openEditor}>Add allocations</Button>}
                        />
                      </td>
                    </tr>
                  ) : null}
                </tbody>
              </table>
            </div>
          </Card>

          <p className="tiny muted">
            Carryover only applies when enabled on both the previous and current month's allocation.
            Refunds reduce spending in their category. Internal transfers never affect budgets.
          </p>
        </>
      ) : null}

      <Modal
        open={wizardOpen}
        title="Build a budget from your reality"
        description="Bills are reserved first, then savings, then whatever you prioritize. Adjust anything afterwards."
        onClose={() => setWizardOpen(false)}
        footer={
          <>
            <Button variant="ghost" type="button" onClick={() => setWizardOpen(false)}>
              Cancel
            </Button>
            <Button
              type="button"
              loading={wizard.isPending}
              onClick={() => {
                setFormError(null);
                if (!wizardIncome || Number(wizardIncome) <= 0) {
                  setFormError("Enter the income you are planning around.");
                  return;
                }
                wizard.mutate();
              }}
            >
              Create budget
            </Button>
          </>
        }
        wide
      >
        <div className="form-grid">
          <Field label="Income to plan around" hint="Use take-home pay, not gross." htmlFor="wiz-income">
            <Input
              id="wiz-income"
              inputMode="decimal"
              value={wizardIncome}
              onChange={(e) => setWizardIncome(e.target.value)}
              placeholder="4800.00"
            />
          </Field>
          <Field label="Savings target (%)" htmlFor="wiz-savings">
            <Input
              id="wiz-savings"
              inputMode="decimal"
              value={wizardSavings}
              onChange={(e) => setWizardSavings(e.target.value)}
            />
          </Field>
        </div>
        <label className="checkbox">
          <input
            type="checkbox"
            checked={wizardIncludeBills}
            onChange={(e) => setWizardIncludeBills(e.target.checked)}
          />
          Reserve this month&apos;s unpaid bills by their category first
        </label>

        <div>
          <p className="field__label" style={{ marginBottom: "0.4rem" }}>
            Priorities (remaining money is shared by weight)
          </p>
          <div className="mapping-grid">
            {categories
              .filter((category) => category.kind === "expense" && category.name !== "Housing")
              .map((category) => (
                <Field key={category.id} label={category.name} htmlFor={`priority-${category.id}`}>
                  <Select
                    id={`priority-${category.id}`}
                    value={String(priorities[category.id] ?? 0)}
                    onChange={(e) =>
                      setPriorities({ ...priorities, [category.id]: Number(e.target.value) })
                    }
                  >
                    <option value="0">No priority</option>
                    <option value="1">Low</option>
                    <option value="2">Medium</option>
                    <option value="3">High</option>
                    <option value="5">Essential</option>
                  </Select>
                </Field>
              ))}
          </div>
        </div>
        {formError ? <div className="form-error">{formError}</div> : null}
      </Modal>

      <Modal
        open={editorOpen && Boolean(budget)}
        title={`Edit ${formatMonth(year, month)} budget`}
        description="Amounts are per month. Set a category to zero to remove its allocation."
        onClose={() => setEditorOpen(false)}
        wide
        footer={
          <>
            <Button variant="ghost" type="button" onClick={() => setEditorOpen(false)}>
              Cancel
            </Button>
            <Button
              type="button"
              loading={saveAllocations.isPending}
              onClick={() => {
                setFormError(null);
                saveAllocations.mutate();
              }}
            >
              Save budget
            </Button>
          </>
        }
      >
        <Field
          label="Planned income for this month"
          hint="Used for the unallocated figure and future wizard runs."
          htmlFor="edit-planned-income"
        >
          <Input
            id="edit-planned-income"
            inputMode="decimal"
            value={plannedIncome}
            onChange={(e) => setPlannedIncome(e.target.value)}
          />
        </Field>
        <div className="mapping-grid">
          {categories.map((category: Category) => {
            const value = allocations[category.id] ?? { amount: "0.00", carryover: false };
            const row = rowsByCategory[category.id];
            return (
              <div key={category.id} className="page-stack" style={{ gap: "0.25rem" }}>
                <Field
                  label={category.name}
                  hint={row ? `${formatMoney(row.spent)} spent` : undefined}
                  htmlFor={`alloc-${category.id}`}
                >
                  <Input
                    id={`alloc-${category.id}`}
                    inputMode="decimal"
                    value={value.amount}
                    onChange={(e) =>
                      setAllocations({
                        ...allocations,
                        [category.id]: { ...value, amount: e.target.value },
                      })
                    }
                  />
                </Field>
                <label className="checkbox">
                  <input
                    type="checkbox"
                    checked={value.carryover}
                    onChange={(e) =>
                      setAllocations({
                        ...allocations,
                        [category.id]: { ...value, carryover: e.target.checked },
                      })
                    }
                  />
                  Carry unused balance forward
                </label>
              </div>
            );
          })}
        </div>
        {formError ? <div className="form-error">{formError}</div> : null}
      </Modal>
    </div>
  );
}
