import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import { useTheme } from "../context/ThemeContext";
import {
  AccountsIcon,
  AssistantIcon,
  BillsIcon,
  BudgetsIcon,
  CalendarIcon,
  ConnectionsIcon,
  DashboardIcon,
  InsightsIcon,
  MoonIcon,
  ReviewIcon,
  ServerIcon,
  SettingsIcon,
  ShoppingIcon,
  SunIcon,
  TransactionsIcon,
} from "./icons";
import { Button } from "./ui";

const NAV = [
  { to: "/", label: "Dashboard", icon: <DashboardIcon />, end: true },
  { to: "/accounts", label: "Accounts", icon: <AccountsIcon /> },
  { to: "/transactions", label: "Transactions", icon: <TransactionsIcon /> },
  { to: "/budgets", label: "Budgets", icon: <BudgetsIcon /> },
  { to: "/bills", label: "Bills", icon: <BillsIcon /> },
  { to: "/calendar", label: "Calendar", icon: <CalendarIcon /> },
  { to: "/shopping", label: "Shopping", icon: <ShoppingIcon /> },
  { to: "/connections", label: "Connections", icon: <ConnectionsIcon /> },
  { to: "/review", label: "Review", icon: <ReviewIcon /> },
  { to: "/insights", label: "Insights", icon: <InsightsIcon /> },
  { to: "/assistant", label: "Assistant", icon: <AssistantIcon /> },
  { to: "/server", label: "Server", icon: <ServerIcon /> },
  { to: "/settings", label: "Settings", icon: <SettingsIcon /> },
];

export function AppShell() {
  const { profile, logout } = useAuth();
  const { theme, setTheme } = useTheme();
  const navigate = useNavigate();

  const today = new Intl.DateTimeFormat("en-US", {
    weekday: "long",
    month: "long",
    day: "numeric",
  }).format(new Date());

  const cycleTheme = () => {
    setTheme(theme === "system" ? "light" : theme === "light" ? "dark" : "system");
  };

  const themeIcon = theme === "dark" ? <MoonIcon /> : theme === "light" ? <SunIcon /> : <span className="tiny mono">A</span>;

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <NavLink to="/" className="brand" aria-label="Personal Finance Companion dashboard">
          <span className="brand__mark" aria-hidden="true">
            ƒ
          </span>
          <span className="brand__name">
            Companion
            <span className="brand__sub">Personal finance</span>
          </span>
        </NavLink>

        <nav className="nav" aria-label="Main">
          <span className="nav__label">Workspace</span>
          {NAV.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.end}
              className={({ isActive }) => `nav__link${isActive ? " is-active" : ""}`}
            >
              <span className="nav__glyph">{item.icon}</span>
              {item.label}
            </NavLink>
          ))}
        </nav>

        <div className="sidebar__footer">
          <div className="sidebar__user">
            <strong>{profile?.user.display_name}</strong>
            {profile?.user.email}
          </div>
          <Button
            variant="ghost"
            size="sm"
            onClick={async () => {
              await logout();
              navigate("/login", { replace: true });
            }}
          >
            Sign out
          </Button>
        </div>
      </aside>

      <div className="main">
        <div className="topbar">
          <span className="topbar__date">{today}</span>
          <div className="topbar__actions">
            <button
              type="button"
              className="icon-button"
              onClick={cycleTheme}
              aria-label={`Theme: ${theme}. Switch theme`}
              title={`Theme: ${theme}`}
            >
              {themeIcon}
            </button>
          </div>
        </div>
        <main className="content" id="main-content">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
