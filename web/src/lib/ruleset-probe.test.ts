import { describe, expect, it } from "vitest";

// Throwaway: exists only to make the Web check fail so the master ruleset can
// be tested against a red pull request. Deleted with this branch.
describe("ruleset probe", () => {
  it("fails on purpose", () => {
    expect(1).toBe(2);
  });
});
