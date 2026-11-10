import { useState, type FormEvent } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../lib/api";
import { formatDate, formatMoney } from "../lib/format";
import type { LocationSettings, ShoppingVisit } from "../lib/types";
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
  Select,
} from "./ui";

const STATUS_TONE = {
  detected: "neutral",
  suggested: "warning",
  confirmed: "positive",
  ignored: "neutral",
} as const;

const VISIT_STATUS_LABEL: Record<ShoppingVisit["status"], string> = {
  detected: "Detected",
  suggested: "Suggested",
  confirmed: "Tracked",
  ignored: "Ignored",
};

/**
 * Location features as the server sees them.
 *
 * The web client cannot read a phone's position, so it configures the feature and
 * manages the history. Geofences themselves are registered by the Android app from
 * the coordinates on each tracked location.
 */
export function ShoppingIntelligence() {
  const queryClient = useQueryClient();
  const [error, setError] = useState<string | null>(null);
  const [locationOpen, setLocationOpen] = useState(false);
  const [clearing, setClearing] = useState(false);
  const [form, setForm] = useState({
    name: "",
    category_id: "",
    monthly_budget: "",
    radius_m: "150",
    notify_enabled: true,
  });

  const settingsQuery = useQuery({ queryKey: ["location-settings"], queryFn: api.locations.settings });
  const locationsQuery = useQuery({ queryKey: ["locations"], queryFn: api.locations.list });
  const visitsQuery = useQuery({ queryKey: ["visits"], queryFn: api.locations.visits });
  const categoriesQuery = useQuery({ queryKey: ["categories"], queryFn: () => api.categories.list(false) });

  const invalidate = () => {
    void queryClient.invalidateQueries({ queryKey: ["location-settings"] });
    void queryClient.invalidateQueries({ queryKey: ["locations"] });
    void queryClient.invalidateQueries({ queryKey: ["visits"] });
    void queryClient.invalidateQueries({ queryKey: ["shopping-context"] });
  };

  const saveSettings = useMutation({
    mutationFn: (body: Partial<LocationSettings> & { pause_minutes?: number }) =>
      api.locations.updateSettings(body),
    onSuccess: invalidate,
    onError: (err) => setError(err instanceof Error ? err.message : "Could not save."),
  });

  const createLocation = useMutation({
    mutationFn: () =>
      api.locations.create({
        name: form.name,
        category_id: form.category_id || null,
        monthly_budget: form.monthly_budget || null,
        radius_m: Number(form.radius_m) || 150,
        notify_enabled: form.notify_enabled,
      }),
    onSuccess: () => {
      setLocationOpen(false);
      setForm({ name: "", category_id: "", monthly_budget: "", radius_m: "150", notify_enabled: true });
      invalidate();
    },
    onError: (err) => setError(err instanceof Error ? err.message : "Could not add the location."),
  });

  const removeLocation = useMutation({
    mutationFn: (id: string) => api.locations.remove(id),
    onSuccess: invalidate,
    onError: (err) => setError(err instanceof Error ? err.message : "Could not remove it."),
  });

  const ignoreVisit = useMutation({
    mutationFn: (id: string) => api.locations.ignoreVisit(id),
    onSuccess: invalidate,
    onError: (err) => setError(err instanceof Error ? err.message : "Could not ignore it."),
  });

  const removeVisit = useMutation({
    mutationFn: (id: string) => api.locations.removeVisit(id),
    onSuccess: invalidate,
    onError: (err) => setError(err instanceof Error ? err.message : "Could not delete it."),
  });

  const clearVisits = useMutation({
    mutationFn: () => api.locations.clearVisits(),
    onSuccess: () => {
      setClearing(false);
      invalidate();
    },
    onError: (err) => setError(err instanceof Error ? err.message : "Could not clear history."),
  });

  const submit = (event: FormEvent) => {
    event.preventDefault();
    setError(null);
    createLocation.mutate();
  };

  if (settingsQuery.isLoading) return <LoadingBlock label="Reading location settings" />;
  const settings = settingsQuery.data;
  if (!settings) {
    return <ErrorBanner message="Could not load location settings." onRetry={() => void settingsQuery.refetch()} />;
  }

  const categories = (categoriesQuery.data ?? []).filter((c) => c.kind === "expense");
  const locations = locationsQuery.data ?? [];
  const visits = visitsQuery.data?.items ?? [];

  return (
    <div className="page-stack">
      {error ? <ErrorBanner message={error} onRetry={() => setError(null)} /> : null}

      <Card>
        <div className="card__title">
          <div>
            <h2 style={{ fontSize: "1.05rem" }}>Shopping Intelligence</h2>
            <p className="tiny muted">
              Off until you turn it on. The Android app checks saved places with the system
              geofencing API; nothing runs in the browser, and no location is shared with an AI
              model.
            </p>
          </div>
          <Badge tone={settings.shopping_intelligence_enabled ? "positive" : "neutral"}>
            {settings.shopping_intelligence_enabled ? "On" : "Off"}
          </Badge>
        </div>

        <div className="page-stack" style={{ gap: "0.55rem", marginTop: "0.8rem" }}>
          <label className="checkbox">
            <input
              type="checkbox"
              checked={settings.location_features_opted_in}
              onChange={(e) =>
                saveSettings.mutate({ location_features_opted_in: e.target.checked })
              }
            />
            I consent to location-aware Shopping Check on this account
          </label>
          <label className="checkbox">
            <input
              type="checkbox"
              checked={settings.shopping_intelligence_enabled}
              disabled={!settings.location_features_opted_in}
              onChange={(e) =>
                saveSettings.mutate({ shopping_intelligence_enabled: e.target.checked })
              }
            />
            Notify me when I arrive at a tracked place
          </label>
          <label className="checkbox">
            <input
              type="checkbox"
              checked={settings.discovery_enabled}
              disabled={!settings.shopping_intelligence_enabled}
              onChange={(e) => saveSettings.mutate({ discovery_enabled: e.target.checked })}
            />
            Suggest places I have not tracked yet
          </label>

          <div className="form-grid" style={{ marginTop: "0.3rem" }}>
            <Field label="Quiet hours start" htmlFor="quiet-start">
              <Input
                id="quiet-start"
                type="time"
                value={settings.quiet_hours_start ?? ""}
                onChange={(e) => saveSettings.mutate({ quiet_hours_start: e.target.value || null })}
              />
            </Field>
            <Field label="Quiet hours end" htmlFor="quiet-end">
              <Input
                id="quiet-end"
                type="time"
                value={settings.quiet_hours_end ?? ""}
                onChange={(e) => saveSettings.mutate({ quiet_hours_end: e.target.value || null })}
              />
            </Field>
            <Field label="Minutes between notifications" htmlFor="cooldown">
              <Select
                id="cooldown"
                value={String(settings.notification_cooldown_minutes)}
                onChange={(e) =>
                  saveSettings.mutate({ notification_cooldown_minutes: Number(e.target.value) })
                }
              >
                <option value="30">30</option>
                <option value="60">60</option>
                <option value="120">120</option>
                <option value="240">240</option>
                <option value="480">480</option>
              </Select>
            </Field>
            <Field label="Keep visit history (days)" htmlFor="retention">
              <Select
                id="retention"
                value={String(settings.visit_history_retention_days)}
                onChange={(e) =>
                  saveSettings.mutate({ visit_history_retention_days: Number(e.target.value) })
                }
              >
                <option value="7">7</option>
                <option value="30">30</option>
                <option value="90">90</option>
                <option value="180">180</option>
              </Select>
            </Field>
          </div>

          <div style={{ display: "flex", gap: "0.4rem", flexWrap: "wrap" }}>
            <Button
              size="sm"
              variant="secondary"
              onClick={() =>
                saveSettings.mutate({ pause_minutes: settings.paused ? 0 : 120 })
              }
            >
              {settings.paused ? "Resume for now" : "Pause for 2 hours"}
            </Button>
            {settings.paused && settings.location_paused_until ? (
              <span className="tiny muted" style={{ alignSelf: "center" }}>
                Paused until {formatDate(settings.location_paused_until, { timeStyle: "short" })}
              </span>
            ) : null}
          </div>
          <p className="tiny muted">{settings.supported.lookup_attribution}</p>
        </div>
      </Card>

      <Card>
        <div className="card__title">
          <div>
            <h2 style={{ fontSize: "1.05rem" }}>Tracked places</h2>
            <p className="tiny muted">
              {locations.length} place(s). Add the store here, then set its coordinates in the
              Android app so a geofence can be registered.
            </p>
          </div>
          <Button size="sm" onClick={() => setLocationOpen(true)}>
            Add place
          </Button>
        </div>

        {locations.length === 0 ? (
          <EmptyState
            title="No tracked places"
            description="Add the shops you want guidance for. Each one can have its own monthly budget and notification setting."
          />
        ) : (
          <ul className="mini-list" style={{ marginTop: "0.7rem" }}>
            {locations.map((location) => (
              <li key={location.id}>
                <div className="mini-list__main">
                  <strong>{location.name}</strong>
                  <span>
                    {location.visit_count} visit(s)
                    {location.last_visit_at
                      ? ` · last ${formatDate(location.last_visit_at, { dateStyle: "medium" })}`
                      : ""}
                    {location.monthly_budget
                      ? ` · ${formatMoney(location.month_spend ?? "0")} of ${formatMoney(location.monthly_budget)} this month`
                      : ""}
                    {!location.notify_enabled ? " · notifications off" : ""}
                  </span>
                </div>
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={() => removeLocation.mutate(location.id)}
                >
                  Remove
                </Button>
              </li>
            ))}
          </ul>
        )}
      </Card>

      <Card>
        <div className="card__title">
          <div>
            <h2 style={{ fontSize: "1.05rem" }}>Visit history</h2>
            <p className="tiny muted">
              A visit means the app noticed you somewhere. It is never a purchase, and the only
              money shown is spending you already recorded.
            </p>
          </div>
          {visits.length ? (
            <Button size="sm" variant="ghost" onClick={() => setClearing(true)}>
              Clear history
            </Button>
          ) : null}
        </div>

        {visits.length === 0 ? (
          <EmptyState
            title="No visits recorded"
            description="Once the Android app is monitoring, arrivals at tracked places and detected new ones appear here."
          />
        ) : (
          <ul className="mini-list" style={{ marginTop: "0.7rem" }}>
            {visits.slice(0, 25).map((visit) => (
              <li key={visit.id}>
                <div className="mini-list__main">
                  <strong>
                    {visit.business_name} <Badge tone={STATUS_TONE[visit.status]}>{VISIT_STATUS_LABEL[visit.status]}</Badge>
                  </strong>
                  <span>
                    {formatDate(visit.visit_day)}
                    {visit.visit_count > 1 ? ` · ${visit.visit_count} visits` : " · first visit"}
                    {visit.transaction_count
                      ? ` · ${visit.transaction_count} purchase(s) ${formatMoney(visit.spend_total)}`
                      : " · no matching purchase"}
                    {visit.distance_m != null ? ` · ${visit.distance_m} m away` : ""}
                  </span>
                </div>
                <div style={{ display: "flex", gap: "0.25rem" }}>
                  {visit.status !== "ignored" ? (
                    <Button size="sm" variant="ghost" onClick={() => ignoreVisit.mutate(visit.id)}>
                      Ignore place
                    </Button>
                  ) : null}
                  <Button size="sm" variant="ghost" onClick={() => removeVisit.mutate(visit.id)}>
                    Delete
                  </Button>
                </div>
              </li>
            ))}
          </ul>
        )}
        {visits.length > 25 ? (
          <p className="tiny muted">Showing the 25 most recent of {visits.length}.</p>
        ) : null}
      </Card>

      <Modal
        open={locationOpen}
        title="Add a tracked place"
        onClose={() => setLocationOpen(false)}
        footer={
          <>
            <Button variant="ghost" type="button" onClick={() => setLocationOpen(false)}>
              Cancel
            </Button>
            <Button type="submit" form="location-form" loading={createLocation.isPending}>
              Add place
            </Button>
          </>
        }
      >
        <form id="location-form" onSubmit={submit} className="page-stack" style={{ gap: "0.8rem" }}>
          <Field label="Place name" htmlFor="loc-name">
            <Input
              id="loc-name"
              required
              value={form.name}
              onChange={(e) => setForm({ ...form, name: e.target.value })}
              placeholder="Target on Perkins"
              maxLength={120}
            />
          </Field>
          <div className="form-grid">
            <Field label="Category" htmlFor="loc-category">
              <Select
                id="loc-category"
                value={form.category_id}
                onChange={(e) => setForm({ ...form, category_id: e.target.value })}
              >
                <option value="">No specific category</option>
                {categories.map((category) => (
                  <option key={category.id} value={category.id}>
                    {category.name}
                  </option>
                ))}
              </Select>
            </Field>
            <Field label="Monthly budget (optional)" htmlFor="loc-budget">
              <Input
                id="loc-budget"
                inputMode="decimal"
                value={form.monthly_budget}
                onChange={(e) => setForm({ ...form, monthly_budget: e.target.value })}
                placeholder="120.00"
              />
            </Field>
            <Field label="Geofence radius (m)" htmlFor="loc-radius" hint="50–2000 metres.">
              <Input
                id="loc-radius"
                inputMode="numeric"
                value={form.radius_m}
                onChange={(e) => setForm({ ...form, radius_m: e.target.value })}
              />
            </Field>
          </div>
          <label className="checkbox">
            <input
              type="checkbox"
              checked={form.notify_enabled}
              onChange={(e) => setForm({ ...form, notify_enabled: e.target.checked })}
            />
            Notify me when I arrive here
          </label>
        </form>
      </Modal>

      <ConfirmDialog
        open={clearing}
        title="Clear location history?"
        message="Every recorded visit is deleted for your account. Tracked places and their budgets are kept."
        confirmLabel="Clear history"
        destructive
        busy={clearVisits.isPending}
        onConfirm={() => clearVisits.mutate()}
        onCancel={() => setClearing(false)}
      />
    </div>
  );
}
