/**
 * The two provider-owned authorisation windows.
 *
 * Neither script is bundled: Teller Connect and Plaid Link are served by the provider so
 * that their UI, their MFA flows and their consent language stay current. Both are loaded
 * on demand, which also means a user who never connects an institution never fetches
 * either one.
 *
 * Nothing here decides which provider is used. The server has already chosen one and
 * returned the parameters for exactly that flow; this module only opens it and hands the
 * result back.
 */

export class ConnectCancelled extends Error {
  constructor() {
    super("Connection cancelled.");
    this.name = "ConnectCancelled";
  }
}

export interface TellerEnrollment {
  accessToken: string;
  user?: { id?: string };
  enrollment?: { id?: string; institution?: { name?: string; id?: string } };
  signatures?: string[];
}

interface TellerConnectInstance {
  open: () => void;
}

interface TellerConnectGlobal {
  setup: (config: Record<string, unknown>) => TellerConnectInstance;
}

interface PlaidGlobal {
  create: (config: Record<string, unknown>) => { open: () => void };
}

declare global {
  interface Window {
    TellerConnect?: TellerConnectGlobal;
    Plaid?: PlaidGlobal;
  }
}

const TELLER_SCRIPT = "https://cdn.teller.io/connect/connect.js";
const PLAID_SCRIPT = "https://cdn.plaid.com/link/v2/stable/link-initialize.js";

const loaded = new Set<string>();

function loadScript(src: string, label: string): Promise<void> {
  if (loaded.has(src)) return Promise.resolve();
  return new Promise((resolve, reject) => {
    const existing = document.querySelector<HTMLScriptElement>(`script[src="${src}"]`);
    const script = existing ?? document.createElement("script");
    const done = () => {
      loaded.add(src);
      resolve();
    };
    script.addEventListener("load", done, { once: true });
    script.addEventListener(
      "error",
      () => reject(new Error(`Could not load ${label}. Check the network and try again.`)),
      { once: true }
    );
    if (!existing) {
      script.src = src;
      script.async = true;
      document.body.appendChild(script);
    }
  });
}

export async function openTellerConnect(params: {
  applicationId: string;
  environment: string;
  products: string[];
  nonce: string;
  institution?: string | null;
}): Promise<TellerEnrollment> {
  await loadScript(TELLER_SCRIPT, "Teller Connect");
  const teller = window.TellerConnect;
  if (!teller) throw new Error("Teller Connect did not initialise.");

  return new Promise<TellerEnrollment>((resolve, reject) => {
    const handle = teller.setup({
      applicationId: params.applicationId,
      environment: params.environment,
      products: params.products,
      // The signed nonce ties the enrolment to this server session.
      nonce: params.nonce,
      ...(params.institution ? { institution: params.institution } : {}),
      onSuccess: (enrollment: TellerEnrollment) => resolve(enrollment),
      onExit: () => reject(new ConnectCancelled()),
    });
    handle.open();
  });
}

export async function openPlaidLink(linkToken: string): Promise<string> {
  await loadScript(PLAID_SCRIPT, "Plaid Link");
  const plaid = window.Plaid;
  if (!plaid) throw new Error("Plaid Link did not initialise.");

  return new Promise<string>((resolve, reject) => {
    const handler = plaid.create({
      token: linkToken,
      onSuccess: (publicToken: string) => resolve(publicToken),
      onExit: (error: unknown) => {
        if (error) reject(new Error("Plaid reported a problem before finishing."));
        else reject(new ConnectCancelled());
      },
    });
    handler.open();
  });
}

/**
 * The fields `/connectivity/connect/finish` needs from a Teller enrolment.
 *
 * Kept as a pure function so the mapping is testable without loading a provider script:
 * the access token is the credential, and the enrolment identity plus signatures are the
 * proof the server verifies.
 */
export function tellerFinishPayload(
  enrollment: TellerEnrollment,
  nonce: string
): {
  public_token: string;
  nonce: string;
  user_id: string | null;
  enrollment_id: string | null;
  signatures: string[];
} {
  return {
    public_token: enrollment.accessToken,
    nonce,
    user_id: enrollment.user?.id ?? null,
    enrollment_id: enrollment.enrollment?.id ?? null,
    signatures: enrollment.signatures ?? [],
  };
}
