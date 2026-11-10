import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ProvidersPage } from "./ProvidersPage";
import type { ProviderAdmin, ProviderOverview } from "../lib/types";

const settings = vi.fn();
const overview = vi.fn();
const update = vi.fn();
const test = vi.fn();

vi.mock("../lib/api", () => ({
  api: {
    server: { settings: () => settings() },
    providerAdmin: {
      overview: () => overview(),
      update: (name: string, body: unknown) => update(name, body),
      test: (name: string) => test(name),
      coverage: vi.fn(),
      setSelection: vi.fn(),
    },
  },
}));

function plaid(overrides: Partial<ProviderAdmin> = {}): ProviderAdmin {
  return {
    name: "plaid",
    label: "Plaid",
    enabled: true,
    priority: 20,
    environment: "sandbox",
    environments: ["sandbox", "production"],
    configured: false,
    usable: false,
    source: "none",
    missing: ["client_id", "secret"],
    problem: null,
    fields: [
      {
        key: "client_id",
        label: "Plaid client ID",
        secret: false,
        required: true,
        multiline: false,
        placeholder: null,
        help: "From the Plaid dashboard.",
        present: false,
        value: null,
        hint: null,
      },
      {
        key: "secret",
        label: "Plaid secret",
        secret: true,
        required: true,
        multiline: false,
        placeholder: null,
        help: "Sandbox secrets work without production approval.",
        present: false,
        value: null,
        hint: null,
      },
    ],
    last_test: null,
    ...overrides,
  };
}

function data(provider: ProviderAdmin = plaid()): ProviderOverview {
  return {
    providers: [provider],
    auto_select: true,
    primary: null,
    any_usable: false,
    sandbox_available: true,
  };
}

function renderPage() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <ProvidersPage />
    </QueryClientProvider>
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  settings.mockResolvedValue({ server: {}, settings: { is_admin: true } });
  overview.mockResolvedValue(data());
  update.mockResolvedValue(plaid());
  test.mockResolvedValue({ ok: true, message: "Connection succeeded.", detail: {} });
});

describe("ProvidersPage credential editor", () => {
  it("keeps typed credentials when a refetch changes the provider", async () => {
    // Two tabs, or a save that lands elsewhere, can flip `configured` while this tab has
    // values typed. That used to remount the card (it was keyed on those props) and wipe
    // them without a word.
    let calls = 0;
    overview.mockImplementation(async () => {
      calls += 1;
      return calls === 1 ? data() : data(plaid({ configured: true, source: "database" }));
    });
    renderPage();

    const clientId = await screen.findByLabelText(/plaid client id/i);
    fireEvent.change(clientId, { target: { value: "client-abc" } });
    fireEvent.change(screen.getByLabelText(/^plaid secret/i), { target: { value: "shh-123" } });

    fireEvent.click(screen.getByRole("button", { name: /test connection/i }));

    // The test refetches the overview; the card must not remount and lose the values.
    await waitFor(() => expect(test).toHaveBeenCalledWith("plaid"));
    await waitFor(() => expect(overview.mock.calls.length).toBeGreaterThan(1));
    expect((screen.getByLabelText(/plaid client id/i) as HTMLInputElement).value).toBe(
      "client-abc"
    );
    expect((screen.getByLabelText(/^plaid secret/i) as HTMLInputElement).value).toBe("shh-123");
  });

  it("saves the typed credentials when the form is submitted", async () => {
    renderPage();

    const clientId = await screen.findByLabelText(/plaid client id/i);
    fireEvent.change(clientId, { target: { value: "client-abc" } });
    fireEvent.change(screen.getByLabelText(/^plaid secret/i), { target: { value: "shh-123" } });

    // Enter in a text field triggers implicit form submission; jsdom does not implement
    // that, so submit the form the way the browser would.
    const save = screen.getByRole("button", { name: /save plaid configuration/i });
    expect(save).toHaveAttribute("type", "submit");
    fireEvent.submit(save.closest("form") as HTMLFormElement);

    await waitFor(() =>
      expect(update).toHaveBeenCalledWith("plaid", {
        enabled: true,
        priority: 20,
        environment: "sandbox",
        credentials: { client_id: "client-abc", secret: "shh-123" },
      })
    );
  });

  it("does not submit the form when a saved credential is removed", async () => {
    overview.mockResolvedValue(
      data(
        plaid({
          configured: true,
          source: "database",
          fields: plaid().fields.map((field) => ({ ...field, present: true })),
        })
      )
    );
    renderPage();

    const remove = await screen.findByRole("button", { name: /remove saved plaid secret/i });
    expect(remove).toHaveAttribute("type", "button");
    fireEvent.click(remove);

    await waitFor(() =>
      expect(update).toHaveBeenCalledWith("plaid", expect.objectContaining({
        credentials: { secret: "" },
      }))
    );
    // Removing a value is its own request, not a full form submit.
    expect(update).toHaveBeenCalledTimes(1);
  });
});
