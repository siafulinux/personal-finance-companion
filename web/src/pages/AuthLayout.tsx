import type { ReactNode } from "react";

export function AuthLayout({
  title,
  subtitle,
  children,
  footer,
}: {
  title: string;
  subtitle: string;
  children: ReactNode;
  footer: ReactNode;
}) {
  return (
    <div className="auth-layout">
      <aside className="auth-aside">
        <div className="auth-aside__brand">
          <span aria-hidden="true">ƒ</span>
          Personal Finance Companion
        </div>
        <div>
          <h1>Know what is actually yours to spend.</h1>
          <p>
            Bills reserved, budgets respected, savings protected. One private ledger for your
            accounts, transactions and plans - with every number explained.
          </p>
        </div>
        <p className="auth-aside__foot">
          Local-first by design. No bank credentials. No data sold. Phase 1.
        </p>
      </aside>
      <main className="auth-main">
        <div className="auth-card">
          <div>
            <h2>{title}</h2>
            <p className="auth-card__sub">{subtitle}</p>
          </div>
          {children}
          <div className="auth-switch">{footer}</div>
        </div>
      </main>
    </div>
  );
}
