import { useMemo, useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../lib/api";
import { formatMoney, todayISO } from "../lib/format";
import { Button, Card, Field, Input, Select } from "../components/ui";
import { useAuth } from "../context/AuthContext";

interface DraftAccount {
  name: string;
  account_type: string;
  opening_balance: string;
  include_in_safe_to_spend: boolean;
}

function timezones(): string[] {
  const intl = Intl as unknown as { supportedValuesOf?: (key: string) => string[] };
  return (
    intl.supportedValuesOf?.("timeZone") ?? [
      "America/New_York",
      "America/Chicago",
      "America/Denver",
      "America/Los_Angeles",
      "Europe/London",
      "UTC",
    ]
  );
}

export function OnboardingPage() {
  const { profile, setProfile } = useAuth();
  const navigate = useNavigate();
  const zones = useMemo(timezones, []);
  const [step, setStep] = useState(0);
  const [displayName, setDisplayName] = useState(profile?.user.display_name ?? "");
  const [timezone, setTimezone] = useState(profile?.user.timezone ?? "America/New_York");
  const [incomeAmount, setIncomeAmount] = useState("2400");
  const [incomeFrequency, setIncomeFrequency] = useState("biweekly");
  const [nextPayday, setNextPayday] = useState("");
  const [buffer, setBuffer] = useState("200");
  const [startingBalance, setStartingBalance] = useState("0");
  const [accounts, setAccounts] = useState<DraftAccount[]>([
    {
      name: "Everyday Checking",
      account_type: "checking",
      opening_balance: "0",
      include_in_safe_to_spend: true,
    },
  ]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const updateAccount = (index: number, patch: Partial<DraftAccount>) => {
    setAccounts((rows) => rows.map((row, i) => (i === index ? { ...row, ...patch } : row)));
  };

  const finish = async (event: FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setError(null);
    const prepared = accounts.map((account, index) => ({
      ...account,
      name: account.name.trim(),
      opening_balance: index === 0 ? startingBalance || "0" : account.opening_balance || "0",
      include_in_safe_to_spend:
        account.account_type === "credit_card" ? false : account.include_in_safe_to_spend,
    }));
    try {
      const next = await api.auth.onboarding({
        display_name: displayName.trim(),
        timezone,
        currency: "USD",
        income_amount: incomeAmount || null,
        income_frequency: incomeAmount ? incomeFrequency : null,
        next_payday: nextPayday || null,
        starting_balance: startingBalance || "0",
        minimum_balance_buffer: buffer || "0",
        accounts: prepared,
        use_default_categories: true,
        seed_budget: false,
      });
      setProfile(next);
      navigate("/", { replace: true });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to save your setup.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="auth-main" style={{ minHeight: "100vh", alignItems: "flex-start", paddingTop: "6vh" }}>
      <form className="auth-card" style={{ width: "min(620px, 100%)" }} onSubmit={finish}>
        <div>
          <p className="eyebrow">Setup · {step + 1} of 3</p>
          <h2 style={{ fontSize: "1.8rem" }}>
            {step === 0
              ? "Let's set your baseline"
              : step === 1
                ? "Income and cash buffer"
                : "Where your money lives"}
          </h2>
          <p className="auth-card__sub">
            {step === 0
              ? "This takes about a minute. You can change everything later."
              : step === 1
                ? "Safe-to-Spend only uses money that has already arrived."
                : "Add the accounts that matter. Credit cards are trackable but never count as cash."}
          </p>
        </div>

        <div className="steps" aria-hidden="true">
          {[0, 1, 2].map((index) => (
            <span
              key={index}
              className={`steps__item ${index === step ? "is-active" : ""} ${index < step ? "is-done" : ""}`}
            />
          ))}
        </div>

        {step === 0 ? (
          <Card className="page-stack" style={{ gap: "0.9rem" }}>
            <Field label="Display name" htmlFor="ob-name">
              <Input
                id="ob-name"
                required
                value={displayName}
                onChange={(e) => setDisplayName(e.target.value)}
                maxLength={120}
              />
            </Field>
            <Field
              label="Timezone"
              hint="Due dates, paydays and monthly budgets follow your local day."
              htmlFor="ob-tz"
            >
              <Select id="ob-tz" value={timezone} onChange={(e) => setTimezone(e.target.value)}>
                {zones.map((zone) => (
                  <option key={zone} value={zone}>
                    {zone.replace(/_/g, " ")}
                  </option>
                ))}
              </Select>
            </Field>
          </Card>
        ) : null}

        {step === 1 ? (
          <Card className="page-stack" style={{ gap: "0.9rem" }}>
            <div className="form-grid">
              <Field label="Take-home pay per paycheck" htmlFor="ob-income">
                <Input
                  id="ob-income"
                  inputMode="decimal"
                  value={incomeAmount}
                  onChange={(e) => setIncomeAmount(e.target.value)}
                  placeholder="2400.00"
                />
              </Field>
              <Field label="Pay frequency" htmlFor="ob-frequency">
                <Select
                  id="ob-frequency"
                  value={incomeFrequency}
                  onChange={(e) => setIncomeFrequency(e.target.value)}
                >
                  <option value="weekly">Weekly</option>
                  <option value="biweekly">Every 2 weeks</option>
                  <option value="semimonthly">Twice a month</option>
                  <option value="monthly">Monthly</option>
                  <option value="irregular">Irregular</option>
                </Select>
              </Field>
              <Field
                label="Next payday"
                hint="Safe-to-Spend reserves bills due before this date."
                htmlFor="ob-payday"
              >
                <Input
                  id="ob-payday"
                  type="date"
                  min={todayISO()}
                  value={nextPayday}
                  onChange={(e) => setNextPayday(e.target.value)}
                />
              </Field>
              <Field
                label="Minimum cash buffer"
                hint="Money you never want to spend, like an emergency floor."
                htmlFor="ob-buffer"
              >
                <Input
                  id="ob-buffer"
                  inputMode="decimal"
                  value={buffer}
                  onChange={(e) => setBuffer(e.target.value)}
                  placeholder="200.00"
                />
              </Field>
            </div>
          </Card>
        ) : null}

        {step === 2 ? (
          <Card className="page-stack" style={{ gap: "0.9rem" }}>
            <div className="form-grid">
              <Field
                label="Starting balance (first account)"
                hint="Your best known current balance. You can adjust it later with an audit trail."
                htmlFor="ob-balance"
              >
                <Input
                  id="ob-balance"
                  inputMode="decimal"
                  value={startingBalance}
                  onChange={(e) => setStartingBalance(e.target.value)}
                  placeholder="1200.00"
                />
              </Field>
              <Field label="First account name" htmlFor="ob-account-name">
                <Input
                  id="ob-account-name"
                  value={accounts[0]?.name ?? ""}
                  onChange={(e) => updateAccount(0, { name: e.target.value })}
                />
              </Field>
            </div>

            <hr className="divider" />
            <div className="section-heading" style={{ marginBottom: 0 }}>
              <h3 style={{ fontSize: "0.98rem" }}>Additional accounts (optional)</h3>
              <Button
                type="button"
                size="sm"
                variant="secondary"
                onClick={() =>
                  setAccounts((rows) => [
                    ...rows,
                    {
                      name: "",
                      account_type: "savings",
                      opening_balance: "0",
                      include_in_safe_to_spend: true,
                    },
                  ])
                }
              >
                Add account
              </Button>
            </div>

            {accounts.slice(1).map((account, index) => {
              const realIndex = index + 1;
              return (
                <div key={realIndex} className="form-grid form-grid--three">
                  <Field label="Name" htmlFor={`acct-name-${realIndex}`}>
                    <Input
                      id={`acct-name-${realIndex}`}
                      value={account.name}
                      onChange={(e) => updateAccount(realIndex, { name: e.target.value })}
                      placeholder="Savings"
                    />
                  </Field>
                  <Field label="Type" htmlFor={`acct-type-${realIndex}`}>
                    <Select
                      id={`acct-type-${realIndex}`}
                      value={account.account_type}
                      onChange={(e) => updateAccount(realIndex, { account_type: e.target.value })}
                    >
                      <option value="checking">Checking</option>
                      <option value="savings">Savings</option>
                      <option value="cash">Cash</option>
                      <option value="digital_wallet">Digital wallet</option>
                      <option value="payment_app">Payment app</option>
                      <option value="credit_card">Credit card</option>
                    </Select>
                  </Field>
                  <Field label="Opening balance" htmlFor={`acct-bal-${realIndex}`}>
                    <Input
                      id={`acct-bal-${realIndex}`}
                      inputMode="decimal"
                      value={account.opening_balance}
                      onChange={(e) => updateAccount(realIndex, { opening_balance: e.target.value })}
                    />
                  </Field>
                </div>
              );
            })}

            <div className="summary-strip">
              <span>
                Account start: <strong>{formatMoney(startingBalance || "0")}</strong>
              </span>
              <span>
                Cash buffer: <strong>{formatMoney(buffer || "0")}</strong>
              </span>
              <span>
                Paycheck: <strong>{formatMoney(incomeAmount || "0")}</strong>
              </span>
            </div>
          </Card>
        ) : null}

        {error ? <div className="form-error" role="alert">{error}</div> : null}

        <div className="form-actions" style={{ justifyContent: "space-between" }}>
          <Button
            type="button"
            variant="ghost"
            onClick={() => setStep((value) => Math.max(0, value - 1))}
            disabled={step === 0 || busy}
          >
            Back
          </Button>
          {step < 2 ? (
            <Button
              type="button"
              onClick={() => setStep((value) => Math.min(2, value + 1))}
              disabled={step === 0 && !displayName.trim()}
            >
              Continue
            </Button>
          ) : (
            <Button type="submit" loading={busy}>
              Open my dashboard
            </Button>
          )}
        </div>
      </form>
    </div>
  );
}
