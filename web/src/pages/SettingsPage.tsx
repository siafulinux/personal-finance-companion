import { useMemo, useState, type FormEvent } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useAuth } from "../context/AuthContext";
import { useTheme, type ThemeChoice } from "../context/ThemeContext";
import { api } from "../lib/api";
import { PasswordForm } from "../components/PasswordForm";
import { formatMoney } from "../lib/format";
import type { Category, IncomeSource } from "../lib/types";
import {
  Badge,
  Button,
  Card,
  Field,
  Input,
  LoadingBlock,
  Modal,
  PageHeader,
  SegmentedControl,
  Select,
} from "../components/ui";

function timezones(): string[] {
  const intl = Intl as unknown as { supportedValuesOf?: (key: string) => string[] };
  return intl.supportedValuesOf?.("timeZone") ?? ["America/New_York", "Europe/London", "UTC"];
}

export function SettingsPage() {
  const { profile, setProfile, logout } = useAuth();
  const { theme, setTheme } = useTheme();
  const queryClient = useQueryClient();
  const zones = useMemo(timezones, []);

  const [displayName, setDisplayName] = useState(profile?.user.display_name ?? "");
  const [timezone, setTimezone] = useState(profile?.user.timezone ?? "UTC");
  const [profileError, setProfileError] = useState<string | null>(null);
  const [profileSaved, setProfileSaved] = useState(false);

  const prefs = profile?.preferences;
  const notifications = profile?.notification_preferences;
  const [buffer, setBuffer] = useState(prefs?.minimum_balance_buffer ?? "0");
  const [horizon, setHorizon] = useState(String(prefs?.safe_to_spend_horizon_days ?? 14));
  const [includePending, setIncludePending] = useState(prefs?.include_pending_debits ?? true);
  const [autoMatch, setAutoMatch] = useState(prefs?.auto_bill_matching ?? true);
  const [toleranceAmount, setToleranceAmount] = useState(prefs?.match_tolerance_amount ?? "2.00");
  const [tolerancePercent, setTolerancePercent] = useState(prefs?.match_tolerance_percent ?? "1.00");
  const [autoThreshold, setAutoThreshold] = useState(prefs?.auto_match_threshold ?? "0.850");
  const [suggestionThreshold, setSuggestionThreshold] = useState(
    prefs?.suggestion_threshold ?? "0.550"
  );
  const [prefsError, setPrefsError] = useState<string | null>(null);
  const [prefsSaved, setPrefsSaved] = useState(false);

  const [shoppingEnabled, setShoppingEnabled] = useState(
    notifications?.shopping_assistant_enabled ?? true
  );
  const [billReminders, setBillReminders] = useState(notifications?.bill_reminders_enabled ?? true);
  const [lowMoney, setLowMoney] = useState(notifications?.low_money_warnings_enabled ?? true);
  const [favoriteStores, setFavoriteStores] = useState(
    notifications?.favorite_store_reminders_enabled ?? false
  );
  const [quietStart, setQuietStart] = useState(notifications?.quiet_hours_start ?? "");
  const [quietEnd, setQuietEnd] = useState(notifications?.quiet_hours_end ?? "");
  const [notifySaved, setNotifySaved] = useState(false);

  const [aliasForm, setAliasForm] = useState({ alias: "", canonical_merchant: "" });
  const [aliasError, setAliasError] = useState<string | null>(null);

  const [newCategory, setNewCategory] = useState("");
  const [newCategoryColor, setNewCategoryColor] = useState("#0f6b5c");
  const [categoryError, setCategoryError] = useState<string | null>(null);

  const [incomeOpen, setIncomeOpen] = useState(false);
  const [editingIncome, setEditingIncome] = useState<IncomeSource | null>(null);
  const [incomeForm, setIncomeForm] = useState({
    name: "",
    amount: "",
    frequency: "biweekly",
    next_payday: "",
  });
  const [incomeError, setIncomeError] = useState<string | null>(null);

  const [deleteOpen, setDeleteOpen] = useState(false);
  const [deletePassword, setDeletePassword] = useState("");
  const [deleteConfirm, setDeleteConfirm] = useState("");
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const [exporting, setExporting] = useState(false);

  const categoriesQuery = useQuery({ queryKey: ["categories", "all"], queryFn: () => api.categories.list(true) });
  const incomeQuery = useQuery({ queryKey: ["income-sources"], queryFn: api.income.list });
  const aliasesQuery = useQuery({ queryKey: ["merchant-aliases"], queryFn: api.bills.aliases });
  const aiQuery = useQuery({ queryKey: ["ai-status"], queryFn: api.insights.aiStatus });

  if (!profile || !prefs || !notifications) return <LoadingBlock label="Loading settings" />;

  const saveProfile = async (event: FormEvent) => {
    event.preventDefault();
    setProfileError(null);
    setProfileSaved(false);
    try {
      const next = await api.auth.updateProfile({ display_name: displayName, timezone });
      setProfile(next);
      setProfileSaved(true);
      void queryClient.invalidateQueries({ queryKey: ["dashboard"] });
    } catch (err) {
      setProfileError(err instanceof Error ? err.message : "Unable to save your profile.");
    }
  };

  const savePreferences = async () => {
    setPrefsError(null);
    setPrefsSaved(false);
    try {
      const updated = await api.auth.updatePreferences({
        minimum_balance_buffer: buffer,
        safe_to_spend_horizon_days: Number(horizon),
        include_pending_debits: includePending,
        auto_bill_matching: autoMatch,
        match_tolerance_amount: toleranceAmount,
        match_tolerance_percent: tolerancePercent,
        auto_match_threshold: autoThreshold,
        suggestion_threshold: suggestionThreshold,
      });
      setProfile({ ...profile, preferences: updated });
      setPrefsSaved(true);
      void queryClient.invalidateQueries({ queryKey: ["dashboard"] });
      void queryClient.invalidateQueries({ queryKey: ["safe-to-spend"] });
    } catch (err) {
      setPrefsError(err instanceof Error ? err.message : "Unable to save preferences.");
    }
  };

  const saveNotifications = async () => {
    try {
      const updated = await api.auth.updateNotifications({
        shopping_assistant_enabled: shoppingEnabled,
        bill_reminders_enabled: billReminders,
        low_money_warnings_enabled: lowMoney,
        favorite_store_reminders_enabled: favoriteStores,
        quiet_hours_start: quietStart || null,
        quiet_hours_end: quietEnd || null,
        quiet_hours_timezone: timezone,
      });
      setProfile({ ...profile, notification_preferences: updated });
      setNotifySaved(true);
    } catch {
      setNotifySaved(false);
    }
  };

  const chooseTheme = async (choice: ThemeChoice) => {
    setTheme(choice);
    try {
      const updated = await api.auth.updatePreferences({ theme: choice });
      setProfile({ ...profile, preferences: updated });
    } catch {
      /* local preference still applies */
    }
  };

  const exportData = async () => {
    setExporting(true);
    try {
      const data = await api.auth.exportData();
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = `finance-export-${new Date().toISOString().slice(0, 10)}.json`;
      anchor.click();
      URL.revokeObjectURL(url);
    } finally {
      setExporting(false);
    }
  };

  const deleteAccount = async () => {
    setDeleteError(null);
    try {
      await api.auth.deleteAccount({ password: deletePassword, confirm: deleteConfirm });
      await logout();
      window.location.assign("/login");
    } catch (err) {
      setDeleteError(err instanceof Error ? err.message : "Unable to delete the account.");
    }
  };

  const categories = categoriesQuery.data ?? [];
  const income = incomeQuery.data ?? [];
  const aliases = aliasesQuery.data ?? [];

  return (
    <div className="page-stack">
      <PageHeader
        eyebrow="Settings"
        title="How your ledger behaves"
        description="Preferences are explicit. Matching thresholds, buffers and notification rules are yours to tune - no hidden defaults doing math behind your back."
      />

      {profile.user.is_demo ? (
        <div className="demo-banner">
          <span>
            <strong>Demo account.</strong> Explore freely. Remove every demo record with{" "}
            <code>pfc seed-demo --remove</code>.
          </span>
          <Badge tone="warning">Demo</Badge>
        </div>
      ) : null}

      <div className="grid grid--two">
        <Card>
          <h2 style={{ fontSize: "1.05rem", marginBottom: "0.8rem" }}>Profile</h2>
          <form className="page-stack" style={{ gap: "0.8rem" }} onSubmit={saveProfile}>
            <Field label="Display name" htmlFor="set-name">
              <Input id="set-name" value={displayName} onChange={(e) => setDisplayName(e.target.value)} />
            </Field>
            <Field label="Email" htmlFor="set-email">
              <Input id="set-email" value={profile.user.email} disabled />
            </Field>
            <Field label="Timezone" hint="Changes when 'today' rolls over for bills and budgets." htmlFor="set-tz">
              <Select id="set-tz" value={timezone} onChange={(e) => setTimezone(e.target.value)}>
                {zones.map((zone) => (
                  <option key={zone} value={zone}>
                    {zone.replace(/_/g, " ")}
                  </option>
                ))}
              </Select>
            </Field>
            <div className="form-actions">
              {profileSaved ? <span className="tiny muted">Saved.</span> : null}
              <Button type="submit">Save profile</Button>
            </div>
            {profileError ? <div className="form-error">{profileError}</div> : null}
          </form>
        </Card>

        <Card>
          <h2 style={{ fontSize: "1.05rem", marginBottom: "0.8rem" }}>Appearance</h2>
          <p className="small muted" style={{ marginBottom: "0.6rem" }}>
            Follow the system, or pin a theme. Both meet accessible contrast targets.
          </p>
          <SegmentedControl
            ariaLabel="Theme"
            value={theme}
            onChange={(value) => void chooseTheme(value)}
            options={[
              { value: "system", label: "System" },
              { value: "light", label: "Light" },
              { value: "dark", label: "Dark" },
            ]}
          />
          <hr className="divider" style={{ margin: "1rem 0" }} />
          <div className="settings-row">
            <div className="settings-row__text">
              <strong>AI features</strong>
              <span>
                {aiQuery.data
                  ? `${aiQuery.data.phase}. Provider: ${aiQuery.data.provider}.`
                  : "Loading status."}
              </span>
            </div>
            <Badge tone={aiQuery.data?.enabled ? "positive" : "neutral"}>
              {aiQuery.data?.enabled ? "Enabled" : "Off (Phase 1)"}
            </Badge>
          </div>
        </Card>
      </div>

      <Card>
        <h2 style={{ fontSize: "1.05rem", marginBottom: "0.3rem" }}>Password</h2>
        <p className="small muted" style={{ marginBottom: "0.9rem" }}>
          Changing your password signs out every other device that is signed in. This browser
          stays signed in.
        </p>
        <PasswordForm
          onSubmit={async (currentPassword, newPassword) => {
            await api.auth.changePassword({
              current_password: currentPassword,
              new_password: newPassword,
            });
          }}
        />
      </Card>

      <Card>
        <h2 style={{ fontSize: "1.05rem", marginBottom: "0.3rem" }}>Safe-to-Spend rules</h2>
        <p className="small muted" style={{ marginBottom: "0.9rem" }}>
          These settings change the deterministic calculation. Every adjustment is reflected in the
          explanation panel on the dashboard.
        </p>
        <div className="form-grid form-grid--three">
          <Field label="Minimum cash buffer" hint="Never recommended for spending." htmlFor="set-buffer">
            <Input id="set-buffer" inputMode="decimal" value={buffer} onChange={(e) => setBuffer(e.target.value)} />
          </Field>
          <Field label="Horizon without payday (days)" htmlFor="set-horizon">
            <Input
              id="set-horizon"
              inputMode="numeric"
              value={horizon}
              onChange={(e) => setHorizon(e.target.value)}
            />
          </Field>
          <Field label="Auto-match threshold" hint="0.85 = unique, high confidence only." htmlFor="set-auto-threshold">
            <Input
              id="set-auto-threshold"
              inputMode="decimal"
              value={autoThreshold}
              onChange={(e) => setAutoThreshold(e.target.value)}
            />
          </Field>
          <Field label="Suggestion threshold" hint="Below this, no match is shown." htmlFor="set-suggest-threshold">
            <Input
              id="set-suggest-threshold"
              inputMode="decimal"
              value={suggestionThreshold}
              onChange={(e) => setSuggestionThreshold(e.target.value)}
            />
          </Field>
          <Field label="Amount tolerance (+/-)" htmlFor="set-tolerance">
            <Input
              id="set-tolerance"
              inputMode="decimal"
              value={toleranceAmount}
              onChange={(e) => setToleranceAmount(e.target.value)}
            />
          </Field>
          <Field label="Percent tolerance (%)" htmlFor="set-tolerance-pct">
            <Input
              id="set-tolerance-pct"
              inputMode="decimal"
              value={tolerancePercent}
              onChange={(e) => setTolerancePercent(e.target.value)}
            />
          </Field>
        </div>
        <div className="page-stack" style={{ gap: "0.5rem", marginTop: "0.8rem" }}>
          <label className="checkbox">
            <input
              type="checkbox"
              checked={includePending}
              onChange={(e) => setIncludePending(e.target.checked)}
            />
            Subtract pending debits from Safe-to-Spend
          </label>
          <label className="checkbox">
            <input type="checkbox" checked={autoMatch} onChange={(e) => setAutoMatch(e.target.checked)} />
            Automatically mark bills paid on unique high-confidence matches
          </label>
        </div>
        <div className="form-actions">
          {prefsSaved ? <span className="tiny muted">Saved.</span> : null}
          <Button type="button" onClick={() => void savePreferences()}>
            Save rules
          </Button>
        </div>
        {prefsError ? <div className="form-error">{prefsError}</div> : null}
      </Card>

      <div className="grid grid--two">
        <Card>
          <h2 style={{ fontSize: "1.05rem", marginBottom: "0.8rem" }}>Notifications</h2>
          <div className="page-stack" style={{ gap: "0.5rem" }}>
            <label className="checkbox">
              <input
                type="checkbox"
                checked={shoppingEnabled}
                onChange={(e) => setShoppingEnabled(e.target.checked)}
              />
              Shopping assistant checks (used by the future Android geofence)
            </label>
            <label className="checkbox">
              <input
                type="checkbox"
                checked={billReminders}
                onChange={(e) => setBillReminders(e.target.checked)}
              />
              Upcoming bill reminders
            </label>
            <label className="checkbox">
              <input type="checkbox" checked={lowMoney} onChange={(e) => setLowMoney(e.target.checked)} />
              Low-money warnings
            </label>
            <label className="checkbox">
              <input
                type="checkbox"
                checked={favoriteStores}
                onChange={(e) => setFavoriteStores(e.target.checked)}
              />
              Favorite-store reminders (reserved for Phase 5)
            </label>
            <div className="form-grid">
              <Field label="Quiet hours start" htmlFor="quiet-start">
                <Input
                  id="quiet-start"
                  type="time"
                  value={quietStart}
                  onChange={(e) => setQuietStart(e.target.value)}
                />
              </Field>
              <Field label="Quiet hours end" htmlFor="quiet-end">
                <Input
                  id="quiet-end"
                  type="time"
                  value={quietEnd}
                  onChange={(e) => setQuietEnd(e.target.value)}
                />
              </Field>
            </div>
            <p className="tiny muted">
              Location features are off. Phase 1 never requests GPS permission or stores location
              history.
            </p>
            <div className="form-actions">
              {notifySaved ? <span className="tiny muted">Saved.</span> : null}
              <Button type="button" variant="secondary" onClick={() => void saveNotifications()}>
                Save notifications
              </Button>
            </div>
          </div>
        </Card>

        <Card>
          <div className="card__title">
            <h2 style={{ fontSize: "1.05rem" }}>Income sources</h2>
            <Button
              size="sm"
              variant="secondary"
              onClick={() => {
                setEditingIncome(null);
                setIncomeForm({ name: "", amount: "", frequency: "biweekly", next_payday: "" });
                setIncomeError(null);
                setIncomeOpen(true);
              }}
            >
              Add
            </Button>
          </div>
          {income.length ? (
            <ul className="mini-list">
              {income.map((source) => (
                <li key={source.id}>
                  <div className="mini-list__main">
                    <strong>{source.name}</strong>
                    <span>
                      {source.frequency.replace(/_/g, " ")}
                      {source.next_payday ? ` · next ${source.next_payday}` : ""}
                    </span>
                  </div>
                  <div style={{ display: "flex", gap: "0.3rem", alignItems: "center" }}>
                    <span className="mini-list__amount">{formatMoney(source.amount)}</span>
                    <Button
                      size="sm"
                      variant="ghost"
                      onClick={() => {
                        setEditingIncome(source);
                        setIncomeForm({
                          name: source.name,
                          amount: source.amount,
                          frequency: source.frequency,
                          next_payday: source.next_payday ?? "",
                        });
                        setIncomeError(null);
                        setIncomeOpen(true);
                      }}
                    >
                      Edit
                    </Button>
                    <Button
                      size="sm"
                      variant="ghost"
                      onClick={async () => {
                        await api.income.remove(source.id);
                        void queryClient.invalidateQueries({ queryKey: ["income-sources"] });
                      }}
                    >
                      Remove
                    </Button>
                  </div>
                </li>
              ))}
            </ul>
          ) : (
            <p className="small muted">
              Add your paycheck so the horizon ends at the next payday instead of a fixed window.
            </p>
          )}
          <p className="tiny muted" style={{ marginTop: "0.6rem" }}>
            Income is never added to Safe-to-Spend before it lands.
          </p>
        </Card>
      </div>

      <div className="grid grid--two">
        <Card>
          <div className="card__title">
            <h2 style={{ fontSize: "1.05rem" }}>Categories</h2>
            <span className="tiny muted">{categories.filter((c) => !c.is_archived).length} active</span>
          </div>
          <form
            className="form-grid"
            style={{ marginBottom: "0.8rem", gridTemplateColumns: "1.5fr 0.8fr 0.7fr" }}
            onSubmit={async (event) => {
              event.preventDefault();
              setCategoryError(null);
              if (!newCategory.trim()) return;
              try {
                await api.categories.create({
                  name: newCategory.trim(),
                  color: newCategoryColor,
                  kind: "expense",
                });
                setNewCategory("");
                void queryClient.invalidateQueries({ queryKey: ["categories"] });
              } catch (err) {
                setCategoryError(err instanceof Error ? err.message : "Unable to add category.");
              }
            }}
          >
            <Field label="New category" htmlFor="new-category">
              <Input
                id="new-category"
                value={newCategory}
                onChange={(e) => setNewCategory(e.target.value)}
                placeholder="Hobbies"
                maxLength={80}
              />
            </Field>
            <Field label="Color" htmlFor="new-category-color">
              <Input
                id="new-category-color"
                type="color"
                value={newCategoryColor}
                onChange={(e) => setNewCategoryColor(e.target.value)}
              />
            </Field>
            <div style={{ display: "flex", alignItems: "flex-end" }}>
              <Button type="submit" size="sm" variant="secondary">
                Add
              </Button>
            </div>
          </form>
          {categoryError ? <div className="form-error">{categoryError}</div> : null}
          <div className="table-wrap" style={{ maxHeight: 300, overflowY: "auto" }}>
            <table className="data">
              <thead>
                <tr>
                  <th>Category</th>
                  <th>Status</th>
                  <th className="is-right">Actions</th>
                </tr>
              </thead>
              <tbody>
                {categories.map((category: Category) => (
                  <tr key={category.id}>
                    <td>
                      <div className="cell-title">
                        <strong>
                          <span className="category-bar__swatch" style={{ background: category.color }} />
                          {category.name}
                        </strong>
                        <span>{category.kind}</span>
                      </div>
                    </td>
                    <td>
                      <Badge tone={category.is_archived ? "neutral" : "positive"}>
                        {category.is_archived ? "Archived" : "Active"}
                      </Badge>
                    </td>
                    <td>
                      <div className="row-actions">
                        {!category.is_archived ? (
                          <Button
                            size="sm"
                            variant="ghost"
                            onClick={async () => {
                              await api.categories.archive(category.id);
                              void queryClient.invalidateQueries({ queryKey: ["categories"] });
                            }}
                          >
                            Archive
                          </Button>
                        ) : null}
                        <Button
                          size="sm"
                          variant="ghost"
                          onClick={async () => {
                            try {
                              await api.categories.remove(category.id);
                              setCategoryError(null);
                            } catch (err) {
                              setCategoryError(
                                err instanceof Error ? err.message : "Unable to delete category."
                              );
                            }
                            void queryClient.invalidateQueries({ queryKey: ["categories"] });
                          }}
                        >
                          Delete
                        </Button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>

        <Card>
          <h2 style={{ fontSize: "1.05rem", marginBottom: "0.4rem" }}>Merchant aliases</h2>
          <p className="small muted" style={{ marginBottom: "0.8rem" }}>
            Teach matching that &quot;XFINITY&quot; is your Comcast bill. Aliases are a strong,
            deterministic signal - never automatic confirmation.
          </p>
          <form
            className="form-grid"
            onSubmit={async (event) => {
              event.preventDefault();
              setAliasError(null);
              if (!aliasForm.alias.trim() || !aliasForm.canonical_merchant.trim()) return;
              try {
                await api.bills.createAlias({
                  alias: aliasForm.alias,
                  canonical_merchant: aliasForm.canonical_merchant,
                });
                setAliasForm({ alias: "", canonical_merchant: "" });
                void queryClient.invalidateQueries({ queryKey: ["merchant-aliases"] });
              } catch (err) {
                setAliasError(err instanceof Error ? err.message : "Unable to add alias.");
              }
            }}
          >
            <Field label="Statement text" htmlFor="alias-alias">
              <Input
                id="alias-alias"
                value={aliasForm.alias}
                onChange={(e) => setAliasForm({ ...aliasForm, alias: e.target.value })}
                placeholder="XFINITY"
              />
            </Field>
            <Field label="Bill merchant" htmlFor="alias-canonical">
              <Input
                id="alias-canonical"
                value={aliasForm.canonical_merchant}
                onChange={(e) => setAliasForm({ ...aliasForm, canonical_merchant: e.target.value })}
                placeholder="Comcast"
              />
            </Field>
            <div className="span-2">
              <Button type="submit" size="sm" variant="secondary">
                Add alias
              </Button>
            </div>
          </form>
          {aliasError ? <div className="form-error">{aliasError}</div> : null}
          <ul className="mini-list">
            {aliases.map((alias) => (
              <li key={alias.id}>
                <div className="mini-list__main">
                  <strong>{alias.alias}</strong>
                  <span>matches {alias.canonical_merchant}</span>
                </div>
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={async () => {
                    await api.bills.removeAlias(alias.id);
                    void queryClient.invalidateQueries({ queryKey: ["merchant-aliases"] });
                  }}
                >
                  Remove
                </Button>
              </li>
            ))}
          </ul>
        </Card>
      </div>

      <Card>
        <h2 style={{ fontSize: "1.05rem", marginBottom: "0.4rem" }}>Your data</h2>
        <p className="small muted" style={{ marginBottom: "0.8rem" }}>
          Export a complete machine-readable copy, or permanently delete this account. Deletion
          requires your password and removes accounts, transactions, budgets, bills and imports.
        </p>
        <div className="settings-section">
          <div className="settings-row">
            <div className="settings-row__text">
              <strong>Export everything</strong>
              <span>JSON containing all records owned by this account.</span>
            </div>
            <Button variant="secondary" onClick={() => void exportData()} loading={exporting}>
              Download JSON
            </Button>
          </div>
          <div className="settings-row">
            <div className="settings-row__text">
              <strong>Sign out</strong>
              <span>Ends this session on this device.</span>
            </div>
            <Button variant="ghost" onClick={() => void logout()}>
              Sign out
            </Button>
          </div>
        </div>
      </Card>

      <Card className="danger-zone">
        <h2 style={{ fontSize: "1.05rem", marginBottom: "0.4rem", color: "var(--danger)" }}>
          Delete account
        </h2>
        <p className="small muted">
          This cannot be undone. Demo data can be removed separately with the CLI.
        </p>
        <div style={{ marginTop: "0.7rem" }}>
          <Button variant="danger" onClick={() => setDeleteOpen(true)}>
            Delete my account
          </Button>
        </div>
      </Card>

      <Modal
        open={incomeOpen}
        title={editingIncome ? "Edit income source" : "Add income source"}
        onClose={() => setIncomeOpen(false)}
        footer={
          <>
            <Button variant="ghost" type="button" onClick={() => setIncomeOpen(false)}>
              Cancel
            </Button>
            <Button
              type="button"
              onClick={async () => {
                setIncomeError(null);
                try {
                  const payload = {
                    name: incomeForm.name,
                    amount: incomeForm.amount,
                    frequency: incomeForm.frequency,
                    next_payday: incomeForm.next_payday || null,
                  };
                  if (editingIncome) {
                    await api.income.update(editingIncome.id, payload);
                  } else {
                    await api.income.create(payload);
                  }
                  setIncomeOpen(false);
                  void queryClient.invalidateQueries({ queryKey: ["income-sources"] });
                  void queryClient.invalidateQueries({ queryKey: ["dashboard"] });
                } catch (err) {
                  setIncomeError(err instanceof Error ? err.message : "Unable to save income.");
                }
              }}
            >
              Save
            </Button>
          </>
        }
      >
        <div className="form-grid">
          <Field label="Name" htmlFor="income-name">
            <Input
              id="income-name"
              value={incomeForm.name}
              onChange={(e) => setIncomeForm({ ...incomeForm, name: e.target.value })}
              placeholder="Paycheck"
            />
          </Field>
          <Field label="Amount" htmlFor="income-amount">
            <Input
              id="income-amount"
              inputMode="decimal"
              value={incomeForm.amount}
              onChange={(e) => setIncomeForm({ ...incomeForm, amount: e.target.value })}
              placeholder="2400.00"
            />
          </Field>
          <Field label="Frequency" htmlFor="income-frequency">
            <Select
              id="income-frequency"
              value={incomeForm.frequency}
              onChange={(e) => setIncomeForm({ ...incomeForm, frequency: e.target.value })}
            >
              <option value="weekly">Weekly</option>
              <option value="biweekly">Every 2 weeks</option>
              <option value="semimonthly">Twice a month</option>
              <option value="monthly">Monthly</option>
              <option value="irregular">Irregular</option>
            </Select>
          </Field>
          <Field label="Next payday" htmlFor="income-payday">
            <Input
              id="income-payday"
              type="date"
              value={incomeForm.next_payday}
              onChange={(e) => setIncomeForm({ ...incomeForm, next_payday: e.target.value })}
            />
          </Field>
        </div>
        {incomeError ? <div className="form-error">{incomeError}</div> : null}
      </Modal>

      <Modal
        open={deleteOpen}
        title="Delete this account permanently?"
        description="Every account, transaction, budget, bill, import and export record will be removed."
        onClose={() => setDeleteOpen(false)}
        footer={
          <>
            <Button variant="ghost" type="button" onClick={() => setDeleteOpen(false)}>
              Cancel
            </Button>
            <Button
              type="button"
              variant="danger"
              onClick={() => void deleteAccount()}
              disabled={deleteConfirm !== "DELETE" || !deletePassword}
            >
              Delete permanently
            </Button>
          </>
        }
      >
        <Field label="Password" htmlFor="delete-password">
          <Input
            id="delete-password"
            type="password"
            value={deletePassword}
            onChange={(e) => setDeletePassword(e.target.value)}
          />
        </Field>
        <Field label='Type DELETE to confirm' htmlFor="delete-confirm">
          <Input
            id="delete-confirm"
            value={deleteConfirm}
            onChange={(e) => setDeleteConfirm(e.target.value)}
            placeholder="DELETE"
          />
        </Field>
        {deleteError ? <div className="form-error">{deleteError}</div> : null}
      </Modal>

      <p className="tiny muted">
        Version {import.meta.env.MODE} · phase 1 · no telemetry, no external analytics.
      </p>
    </div>
  );
}
