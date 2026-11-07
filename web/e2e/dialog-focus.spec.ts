/**
 * Real-browser coverage for dialog focus and selection-on-open.
 *
 * `web/src/components/ui.test.tsx` covers the logic in jsdom, but jsdom does not
 * implement a browser's own typing, so it cannot show that a selected value is
 * actually replaced by the next key — or that a caret survives React re-rendering
 * on every keystroke. These tests drive Chromium with real key events against
 * `e2e/harness/index.html`, which mounts the real `Modal`.
 */
import { expect, test, type Locator } from "@playwright/test";

const HARNESS = "/e2e/harness/index.html";

/** The live selection range the browser holds for a text field. */
async function selection(locator: Locator): Promise<(number | null)[]> {
  return locator.evaluate((element) => {
    const input = element as HTMLInputElement;
    return [input.selectionStart, input.selectionEnd];
  });
}

test.describe("dialog focus and selection", () => {
  let pageErrors: string[];

  test.beforeEach(async ({ page }) => {
    pageErrors = [];
    page.on("pageerror", (error) => pageErrors.push(error.message));
    await page.goto(HARNESS);
  });

  test.afterEach(() => {
    expect(pageErrors, "the page threw during this test").toEqual([]);
  });

  test("an edit dialog selects its saved value, so one key press replaces it", async ({ page }) => {
    await page.getByRole("button", { name: "Edit transaction" }).click();

    const amount = page.locator("#amount");
    // Focus is moved when the dialog opens, with no click into the field.
    await expect(amount).toBeFocused();
    await expect(amount).toHaveValue("128.00");
    expect(await selection(amount)).toEqual([0, "128.00".length]);

    // A single real key press replaces the whole selected value.
    await page.keyboard.type("7");

    await expect(amount).toHaveValue("7");
    await expect(amount).toBeFocused();
    // Selection-on-open must not touch the dialog's other fields.
    await expect(page.locator("#description")).toHaveValue("Groceries");
    await expect(page.locator("#notes")).toHaveValue("Weekly shop");
  });

  test("an add dialog opens empty with a collapsed caret, so typing appends", async ({ page }) => {
    await page.getByRole("button", { name: "Add transaction" }).click();

    const amount = page.locator("#amount");
    await expect(amount).toBeFocused();
    await expect(amount).toHaveValue("");
    expect(await selection(amount)).toEqual([0, 0]);

    await page.keyboard.type("42.50");

    await expect(amount).toHaveValue("42.50");
    expect(await selection(amount)).toEqual(["42.50".length, "42.50".length]);
  });

  test("every character reaches the field while React re-renders on each keystroke", async ({
    page,
  }) => {
    await page.getByRole("button", { name: "Edit transaction" }).click();

    const amount = page.locator("#amount");
    await expect(amount).toBeFocused();

    // Select-all then type over it, the way a person corrects an amount.
    await page.keyboard.press("ControlOrMeta+a");
    await page.keyboard.type("1250.75", { delay: 40 });

    await expect(amount).toHaveValue("1250.75");
    await expect(amount).toBeFocused();

    // Backspace and arrow keys are ordinary editing tools, not dialog shortcuts.
    await page.keyboard.press("Backspace");
    await expect(amount).toHaveValue("1250.7");
    await page.keyboard.press("Home");
    await page.keyboard.press("Delete");
    await expect(amount).toHaveValue("250.7");
    await expect(amount).toBeFocused();
  });

  test("spaces, punctuation and slash are inserted literally", async ({ page }) => {
    await page.getByRole("button", { name: "Add transaction" }).click();
    await expect(page.locator("#description")).not.toBeFocused();

    await page.locator("#description").click();
    await page.keyboard.type("Coffee & tea / snacks 2.50");

    await expect(page.locator("#description")).toHaveValue("Coffee & tea / snacks 2.50");
    await expect(page.locator("#description")).toBeFocused();
  });

  test("a date field takes focus, keeps its value, and does not error", async ({ page }) => {
    await page.getByRole("button", { name: "Change date" }).click();

    const date = page.locator("#due-date");
    // Browsers refuse a selection range on date inputs; focus alone is expected.
    await expect(date).toBeFocused();
    await expect(date).toHaveValue("2026-11-07");
  });

  test("Escape closes the dialog from the keyboard", async ({ page }) => {
    await page.getByRole("button", { name: "Edit transaction" }).click();
    await expect(page.locator("#amount")).toBeFocused();

    await page.keyboard.press("Escape");

    await expect(page.locator('[role="dialog"]')).toHaveCount(0);
    await expect(page.locator("#state")).toHaveText("closed");
  });
});
