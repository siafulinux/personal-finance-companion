import { describe, expect, it } from "vitest";
import {
  daysBetween,
  formatDate,
  formatMoney,
  formatPercent,
  formatSignedMoney,
  parseMonth,
  relativeDueLabel,
} from "./format";

describe("money formatting", () => {
  it("formats cents exactly", () => {
    expect(formatMoney("310.00")).toBe("$310.00");
    expect(formatMoney("0")).toBe("$0.00");
  });

  it("keeps negative amounts explicit", () => {
    expect(formatSignedMoney("-12.5")).toBe("-$12.50");
    expect(formatSignedMoney("7")).toBe("$7.00");
  });

  it("handles missing values", () => {
    expect(formatMoney(null)).toBe("—");
    expect(formatMoney("not-a-number")).toBe("—");
  });

  it("formats percentages without float noise", () => {
    expect(formatPercent("65.00")).toBe("65%");
    expect(formatPercent("12.345", 1)).toBe("12.3%");
  });
});

describe("date helpers", () => {
  it("computes day differences across month boundaries", () => {
    expect(daysBetween("2026-10-31", "2026-11-02")).toBe(2);
    expect(daysBetween("2026-11-02", "2026-10-30")).toBe(-3);
  });

  it("describes due dates relative to today", () => {
    expect(relativeDueLabel("2026-11-02", "2026-11-02")).toBe("Due today");
    expect(relativeDueLabel("2026-11-03", "2026-11-02")).toBe("Due tomorrow");
    expect(relativeDueLabel("2026-10-31", "2026-11-02")).toBe("Overdue by 2 days");
    expect(relativeDueLabel("2026-11-08", "2026-11-02")).toBe("Due in 6 days");
  });

  it("parses month inputs", () => {
    expect(parseMonth("2026-02")).toEqual({ year: 2026, month: 2 });
  });

  it("formats plain dates with a year by default", () => {
    expect(formatDate("2026-11-06")).toBe("Nov 6, 2026");
    expect(formatDate(null)).toBe("—");
  });

  it("formats timestamps with style presets without throwing", () => {
    // dateStyle/timeStyle cannot be mixed with day/month parts; a regression here
    // blanked the whole Connections page on the sync history.
    const rendered = formatDate("2026-11-06T14:32:00+00:00", {
      dateStyle: "medium",
      timeStyle: "short",
    });
    expect(rendered).toContain("2026");
    expect(rendered).toMatch(/\d/);
  });
});
