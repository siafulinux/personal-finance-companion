/**
 * Fail closed when the suite claims to run on a shifted clock but does not.
 *
 * `Web on a shifted clock` runs `npm test` under libfaketime with `TODAY` naming
 * the instant it should pretend it is, because the UI formats dates for a living:
 * "Due today", "in 5 days", month headings, the calendar grid. A preload that
 * failed to install, an `LD_PRELOAD` path that resolves to nothing, or a wrapper
 * that falls back to the real clock leaves the suite running on today's date,
 * where it passes for the wrong reason and the job proves nothing.
 *
 * The job checks the shift for one `node -e` call before running the suite. This
 * test checks it for the process the tests actually run in -- and because vitest
 * runs files in child processes, a shift visible here is also proof that it was
 * inherited rather than applied to the launcher only.
 *
 * The first test needs no shift, so the file cannot pass by being vacuous.
 */
import { describe, expect, it } from "vitest";

const TODAY = (process.env.TODAY ?? "").trim();

// libfaketime holds the offset rather than freezing the clock, so a run legitimately
// advances from the instant it was given. Five minutes is far more than the suite
// takes and still rejects "roughly today", which is what a broken preload produces.
const TOLERANCE_MS = 5 * 60 * 1000;

function expectedInstant(): Date {
  const match = /^(\d{4})-(\d{2})-(\d{2}) (\d{2}):(\d{2}):(\d{2})$/.exec(TODAY);
  if (!match) {
    throw new Error(
      `TODAY=${JSON.stringify(TODAY)} is not a 'YYYY-MM-DD HH:MM:SS' instant, so the clock ` +
        "this job claims to test cannot be verified.",
    );
  }
  const [, year, month, day, hour, minute, second] = match;
  // libfaketime reads the value as local time, so build a local Date: whether the
  // runner's zone is UTC or not, "the clock is shifted" keeps its meaning.
  return new Date(
    Number(year),
    Number(month) - 1,
    Number(day),
    Number(hour),
    Number(minute),
    Number(second),
  );
}

/** Describe how `observed` fails to be the shifted clock, or null if it is it. */
function mismatch(expected: Date, observed: Date): string | null {
  if (observed.toDateString() !== expected.toDateString()) {
    return `the date is ${observed.toDateString()}, not ${expected.toDateString()}`;
  }
  const drift = Math.abs(observed.getTime() - expected.getTime());
  if (drift > TOLERANCE_MS) {
    return `the clock is ${Math.round(drift / 1000)}s away from ${expected.toString()}`;
  }
  return null;
}

describe("shifted clock", () => {
  it("rejects the real clock", () => {
    const expected = new Date(2028, 1, 29, 12, 0, 0);
    // Exactly what a broken preload looks like: today's date, not the leap day.
    expect(mismatch(expected, new Date(2026, 10, 14, 9, 30))).not.toBeNull();
    // A clock inside the tolerance is accepted, or the check would fail on drift.
    expect(mismatch(expected, new Date(expected.getTime() + TOLERANCE_MS / 2))).toBeNull();
  });

  it.skipIf(!TODAY)("runs this process on the shifted clock", () => {
    const expected = expectedInstant();

    const problem = mismatch(expected, new Date());
    expect(
      problem,
      `libfaketime did not take effect in this process: ${problem}. ` +
        `TODAY=${JSON.stringify(TODAY)}. Every date-dependent test in this run is ` +
        "therefore reading the real clock, so this job proves nothing.",
    ).toBeNull();

    // Date.now() and the Date constructor read the same epoch clock, but a shim
    // around one of them would show up here rather than as a later mystery.
    const epochDrift = Math.abs(Date.now() - expected.getTime());
    expect(epochDrift).toBeLessThanOrEqual(TOLERANCE_MS);
  });
});
