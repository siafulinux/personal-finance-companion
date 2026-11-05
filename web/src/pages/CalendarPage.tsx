import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "../lib/api";
import { formatDate, formatMoney, formatMonth, relativeDueLabel, todayISO } from "../lib/format";
import type { Occurrence } from "../lib/types";
import {
  Badge,
  Button,
  EmptyState,
  ErrorBanner,
  LoadingBlock,
  Modal,
  PageHeader,
} from "../components/ui";

const WEEKDAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];

function buildGrid(year: number, month: number) {
  const first = new Date(year, month - 1, 1);
  const start = new Date(year, month - 1, 1 - first.getDay());
  return Array.from({ length: 42 }, (_, index) => {
    const date = new Date(start.getFullYear(), start.getMonth(), start.getDate() + index);
    return {
      iso: `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`,
      day: date.getDate(),
      inMonth: date.getMonth() === month - 1,
    };
  });
}

export function CalendarPage() {
  const today = todayISO();
  const now = new Date();
  const [year, setYear] = useState(now.getFullYear());
  const [month, setMonth] = useState(now.getMonth() + 1);
  const [selected, setSelected] = useState<string | null>(null);

  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ["bill-calendar", year, month],
    queryFn: () => api.bills.calendar(year, month),
  });

  const byDate = useMemo(() => {
    const map: Record<string, Occurrence[]> = {};
    data?.occurrences.forEach((occurrence) => {
      map[occurrence.due_date] = [...(map[occurrence.due_date] ?? []), occurrence];
    });
    return map;
  }, [data]);

  const grid = useMemo(() => buildGrid(year, month), [year, month]);
  const shift = (delta: number) => {
    const next = new Date(year, month - 1 + delta, 1);
    setYear(next.getFullYear());
    setMonth(next.getMonth() + 1);
  };

  const selectedOccurrences = selected ? byDate[selected] ?? [] : [];

  return (
    <div className="page-stack">
      <PageHeader
        eyebrow="Calendar"
        title="The month, mapped"
        description="Every bill occurrence in one view. Paid occurrences are dimmed; overdue ones are marked so nothing slips."
        actions={
          <>
            <Button variant="secondary" size="sm" onClick={() => shift(-1)}>
              ← Previous
            </Button>
            <Button
              variant="secondary"
              size="sm"
              onClick={() => {
                const current = new Date();
                setYear(current.getFullYear());
                setMonth(current.getMonth() + 1);
              }}
            >
              Today
            </Button>
            <Button variant="secondary" size="sm" onClick={() => shift(1)}>
              Next →
            </Button>
          </>
        }
      />

      <div className="section-heading">
        <h2>{formatMonth(year, month)}</h2>
        {data ? (
          <p className="small muted">
            {formatMoney(data.totals.remaining ?? "0")} still due · {data.totals.count} occurrence(s)
          </p>
        ) : null}
      </div>

      {error ? (
        <ErrorBanner
          message={error instanceof Error ? error.message : "Unable to load the calendar."}
          onRetry={() => void refetch()}
        />
      ) : null}

      {isLoading ? (
        <LoadingBlock label="Loading calendar" />
      ) : (
        <div className="calendar">
          <div className="calendar__weekdays">
            {WEEKDAYS.map((day) => (
              <span key={day}>{day}</span>
            ))}
          </div>
          <div className="calendar__grid">
            {grid.map((cell) => {
              const events = byDate[cell.iso] ?? [];
              const unpaid = events.filter((event) => event.status !== "paid" && event.status !== "skipped");
              const total = unpaid.reduce((sum, event) => sum + Number(event.remaining_amount), 0);
              return (
                <button
                  key={cell.iso}
                  type="button"
                  className={`calendar__day ${cell.inMonth ? "" : "is-outside"} ${
                    cell.iso === today ? "is-today" : ""
                  }`}
                  onClick={() => setSelected(cell.iso)}
                  aria-label={`${formatDate(cell.iso)}${events.length ? `, ${events.length} bill occurrences` : ""}`}
                >
                  <span className="calendar__daynum">{cell.day}</span>
                  {events.slice(0, 3).map((event) => (
                    <span
                      key={event.id}
                      className={`calendar__event ${event.is_overdue ? "is-overdue" : ""} ${
                        event.status === "paid" ? "is-paid" : ""
                      }`}
                      title={`${event.bill_name} · ${formatMoney(event.remaining_amount)}`}
                    >
                      {event.bill_name}
                    </span>
                  ))}
                  {events.length > 3 ? (
                    <span className="tiny muted">+{events.length - 3} more</span>
                  ) : null}
                  {total > 0 ? (
                    <span className="tiny mono muted" style={{ marginTop: "auto" }}>
                      {formatMoney(total)}
                    </span>
                  ) : null}
                </button>
              );
            })}
          </div>
        </div>
      )}

      <p className="tiny muted">
        Occurrences are generated from each bill&apos;s anchor date and schedule. Editing a bill updates
        only future, unpaid occurrences so history stays intact.
      </p>

      <Modal
        open={Boolean(selected)}
        title={selected ? formatDate(selected, { weekday: "long", month: "long", day: "numeric", year: "numeric" }) : "Day"}
        onClose={() => setSelected(null)}
      >
        {selectedOccurrences.length ? (
          <div className="page-stack" style={{ gap: "0.6rem" }}>
            {selectedOccurrences.map((occurrence) => (
              <div key={occurrence.id} className="bill-row">
                <div>
                  <div className="bill-row__name">{occurrence.bill_name}</div>
                  <div className="bill-row__sub">
                    {occurrence.is_overdue ? relativeDueLabel(occurrence.due_date, today) : occurrence.status}
                    {occurrence.status === "partial"
                      ? ` · paid ${formatMoney(occurrence.paid_amount)}`
                      : ""}
                  </div>
                </div>
                <div style={{ textAlign: "right" }}>
                  <div className="mini-list__amount">{formatMoney(occurrence.remaining_amount)}</div>
                  <Badge
                    tone={
                      occurrence.status === "paid"
                        ? "positive"
                        : occurrence.is_overdue
                          ? "danger"
                          : "neutral"
                    }
                  >
                    {occurrence.status}
                  </Badge>
                </div>
              </div>
            ))}
            <p className="tiny muted">
              Manage payments from Bills: mark paid, record a partial payment, or skip this occurrence.
            </p>
          </div>
        ) : (
          <EmptyState
            title="Nothing due"
            description="No bill occurrences fall on this day."
          />
        )}
      </Modal>
    </div>
  );
}
