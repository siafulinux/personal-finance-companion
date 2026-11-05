import { Navigate, Outlet, Route, Routes } from "react-router-dom";
import { AppShell } from "./components/AppShell";
import { LoadingBlock } from "./components/ui";
import { useAuth } from "./context/AuthContext";
import { AccountsPage } from "./pages/AccountsPage";
import { BillsPage } from "./pages/BillsPage";
import { BudgetsPage } from "./pages/BudgetsPage";
import { CalendarPage } from "./pages/CalendarPage";
import { DashboardPage } from "./pages/DashboardPage";
import { LoginPage } from "./pages/LoginPage";
import { OnboardingPage } from "./pages/OnboardingPage";
import { RegisterPage } from "./pages/RegisterPage";
import { SettingsPage } from "./pages/SettingsPage";
import { ShoppingPage } from "./pages/ShoppingPage";
import { TransactionsPage } from "./pages/TransactionsPage";

function FullScreenLoader() {
  return (
    <div style={{ minHeight: "100vh", display: "grid", placeItems: "center" }}>
      <LoadingBlock label="Opening your ledger" />
    </div>
  );
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
          <Route path="/calendar" element={<CalendarPage />} />
          <Route path="/shopping" element={<ShoppingPage />} />
          <Route path="/settings" element={<SettingsPage />} />
        </Route>
      </Route>

      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
