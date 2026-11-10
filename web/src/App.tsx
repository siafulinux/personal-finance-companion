import { useEffect, useState, type ReactNode } from "react";
import { Navigate, Outlet, Route, Routes } from "react-router-dom";
import { AppShell } from "./components/AppShell";
import { Button, Card, LoadingBlock } from "./components/ui";
import { useAuth } from "./context/AuthContext";
import { api } from "./lib/api";
import type { ServerInfo } from "./lib/types";
import { AccountsPage } from "./pages/AccountsPage";
import { AssistantPage } from "./pages/AssistantPage";
import { BillsPage } from "./pages/BillsPage";
import { BudgetsPage } from "./pages/BudgetsPage";
import { CalendarPage } from "./pages/CalendarPage";
import { ConnectionsPage } from "./pages/ConnectionsPage";
import { DashboardPage } from "./pages/DashboardPage";
import { InsightsPage } from "./pages/InsightsPage";
import { LoansPage } from "./pages/LoansPage";
import { LoginPage } from "./pages/LoginPage";
import { ObligationsPage } from "./pages/ObligationsPage";
import { OnboardingPage } from "./pages/OnboardingPage";
import { ProvidersPage } from "./pages/ProvidersPage";
import { RegisterPage } from "./pages/RegisterPage";
import { ReviewPage } from "./pages/ReviewPage";
import { SavingsPage } from "./pages/SavingsPage";
import { ServerPage } from "./pages/ServerPage";
import { SettingsPage } from "./pages/SettingsPage";
import { SetupPage } from "./pages/SetupPage";
import { ShoppingPage } from "./pages/ShoppingPage";
import { TransactionsPage } from "./pages/TransactionsPage";

function FullScreenLoader() {
  return (
    <div style={{ minHeight: "100vh", display: "grid", placeItems: "center" }}>
      <LoadingBlock label="Opening your ledger" />
    </div>
  );
}

function ServerUnreachable({ message }: { message: string }) {
  return (
    <div style={{ minHeight: "100vh", display: "grid", placeItems: "center", padding: "1rem" }}>
      <Card style={{ maxWidth: 460 }}>
        <h2 style={{ fontSize: "1.1rem", marginBottom: "0.4rem" }}>Cannot reach this server</h2>
        <p className="tiny muted" style={{ marginBottom: "1rem" }}>
          {message} If the stack was just started, wait a moment and try again.
        </p>
        <Button onClick={() => window.location.reload()}>Try again</Button>
      </Card>
    </div>
  );
}

/**
 * Reads the public server info once per load. A server with no accounts shows
 * the first-run wizard instead of a login form; anything else proceeds to the
 * normal routes.
 */
function ServerGate({ children }: { children: ReactNode }) {
  const [info, setInfo] = useState<ServerInfo | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    api.server
      .info()
      .then((next) => {
        if (!cancelled) setInfo(next);
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "The server did not answer.");
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  if (error) return <ServerUnreachable message={error} />;
  if (!info) return <FullScreenLoader />;
  if (info.setup_required) return <SetupPage />;
  return <>{children}</>;
}

function RequireAuth() {
  const { profile, loading } = useAuth();
  if (loading) return <FullScreenLoader />;
  if (!profile) return <Navigate to="/login" replace />;
  if (!profile.user.onboarding_completed_at) return <Navigate to="/onboarding" replace />;
  return <Outlet />;
}

function RequireOnboarding() {
  const { profile, loading } = useAuth();
  if (loading) return <FullScreenLoader />;
  if (!profile) return <Navigate to="/login" replace />;
  return <Outlet />;
}

function PublicOnly() {
  const { profile, loading } = useAuth();
  if (loading) return <FullScreenLoader />;
  if (profile) {
    return (
      <Navigate to={profile.user.onboarding_completed_at ? "/" : "/onboarding"} replace />
    );
  }
  return <Outlet />;
}

export function App() {
  return (
    <ServerGate>
      <Routes>
      <Route element={<PublicOnly />}>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/register" element={<RegisterPage />} />
      </Route>

      <Route element={<RequireOnboarding />}>
        <Route path="/onboarding" element={<OnboardingPage />} />
      </Route>

      <Route element={<RequireAuth />}>
        <Route element={<AppShell />}>
          <Route index element={<DashboardPage />} />
          <Route path="/accounts" element={<AccountsPage />} />
          <Route path="/transactions" element={<TransactionsPage />} />
          <Route path="/budgets" element={<BudgetsPage />} />
          <Route path="/bills" element={<BillsPage />} />
          <Route path="/obligations" element={<ObligationsPage />} />
          <Route path="/loans" element={<LoansPage />} />
          <Route path="/savings" element={<SavingsPage />} />
          <Route path="/calendar" element={<CalendarPage />} />
          <Route path="/shopping" element={<ShoppingPage />} />
          <Route path="/connections" element={<ConnectionsPage />} />
          <Route path="/review" element={<ReviewPage />} />
          <Route path="/insights" element={<InsightsPage />} />
          <Route path="/assistant" element={<AssistantPage />} />
          <Route path="/server" element={<ServerPage />} />
          <Route path="/server/providers" element={<ProvidersPage />} />
          <Route path="/settings" element={<SettingsPage />} />
        </Route>
      </Route>

      <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </ServerGate>
  );
}
