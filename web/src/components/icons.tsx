const common = {
  fill: "none",
  stroke: "currentColor",
  strokeWidth: 1.6,
  strokeLinecap: "round" as const,
  strokeLinejoin: "round" as const,
};

export function ConnectionsIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true" {...common}>
      <path d="M9.5 14.5 14.5 9.5" />
      <path d="M11 6.5 12.8 4.7a3.9 3.9 0 0 1 5.5 5.5L16.5 12" />
      <path d="M13 17.5l-1.8 1.8a3.9 3.9 0 0 1-5.5-5.5L7.5 12" />
    </svg>
  );
}

export function ProvidersIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true" {...common}>
      <path d="M4 8.5 12 4l8 4.5v7L12 20l-8-4.5Z" />
      <path d="M12 11.5v8.5" />
      <path d="M4 8.5 12 13l8-4.5" />
    </svg>
  );
}

export function ServerIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true" {...common}>
      <rect x="3.5" y="4" width="17" height="6" rx="1.6" />
      <rect x="3.5" y="14" width="17" height="6" rx="1.6" />
      <path d="M7 7h.01M7 17h.01" />
    </svg>
  );
}

export function ReviewIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true" {...common}>
      <path d="M9 3.5h6a2 2 0 0 1 2 2V20a1 1 0 0 1-1 1H8a1 1 0 0 1-1-1V5.5a2 2 0 0 1 2-2Z" />
      <path d="M9.5 8.5h5" />
      <path d="M9.5 12h5" />
      <path d="M9.5 15.5h3" />
    </svg>
  );
}

export function InsightsIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true" {...common}>
      <path d="M4 19V5" />
      <path d="M4 19h16" />
      <path d="M8 16v-4" />
      <path d="M12.5 16V8" />
      <path d="M17 16v-6" />
    </svg>
  );
}

export function AssistantIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true" {...common}>
      <path d="M4 5.5h16v10H9l-4 3.5v-13.5Z" />
      <path d="M8.5 10.5h7" />
    </svg>
  );
}

export function DashboardIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true" {...common}>
      <rect x="3" y="3" width="7.5" height="7.5" rx="1.4" />
      <rect x="13.5" y="3" width="7.5" height="7.5" rx="1.4" />
      <rect x="3" y="13.5" width="7.5" height="7.5" rx="1.4" />
      <rect x="13.5" y="13.5" width="7.5" height="7.5" rx="1.4" />
    </svg>
  );
}

export function AccountsIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true" {...common}>
      <rect x="3" y="6" width="18" height="13" rx="2.4" />
      <path d="M3 10h18" />
      <path d="M16 15h2" />
      <path d="M7 6V5a2 2 0 0 1 2-2h7" />
    </svg>
  );
}

export function TransactionsIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true" {...common}>
      <path d="M4 8h13" />
      <path d="M14 5l3 3-3 3" />
      <path d="M20 16H7" />
      <path d="M10 13l-3 3 3 3" />
    </svg>
  );
}

export function BudgetsIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true" {...common}>
      <path d="M4 20V10" />
      <path d="M10 20V4" />
      <path d="M16 20v-7" />
      <path d="M22 20V8" />
    </svg>
  );
}

export function BillsIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true" {...common}>
      <path d="M6 3h12v18l-3-2-3 2-3-2-3 2V3z" />
      <path d="M9 8h6" />
      <path d="M9 12h6" />
    </svg>
  );
}

export function CalendarIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true" {...common}>
      <rect x="3" y="5" width="18" height="16" rx="2.2" />
      <path d="M3 10h18M8 3v4M16 3v4" />
      <path d="M8 14h2M14 14h2M8 17h2" />
    </svg>
  );
}

export function ShoppingIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true" {...common}>
      <path d="M5 8h14l-1.2 12H6.2L5 8z" />
      <path d="M9 8V6a3 3 0 0 1 6 0v2" />
    </svg>
  );
}

export function SettingsIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true" {...common}>
      <circle cx="12" cy="12" r="3.2" />
      <path d="M19.4 15a1.7 1.7 0 0 0 .34 1.88l.06.06-2.2 2.2-.06-.06a1.7 1.7 0 0 0-1.88-.34 1.7 1.7 0 0 0-1.03 1.56V21h-3.1v-.7a1.7 1.7 0 0 0-1.03-1.56 1.7 1.7 0 0 0-1.88.34l-.06.06-2.2-2.2.06-.06A1.7 1.7 0 0 0 4.6 15a1.7 1.7 0 0 0-1.56-1.03H2.3v-3.1h.74A1.7 1.7 0 0 0 4.6 9.84a1.7 1.7 0 0 0-.34-1.88l-.06-.06 2.2-2.2.06.06a1.7 1.7 0 0 0 1.88.34A1.7 1.7 0 0 0 9.37 4.5V3h3.1v1.5a1.7 1.7 0 0 0 1.03 1.56 1.7 1.7 0 0 0 1.88-.34l.06-.06 2.2 2.2-.06.06a1.7 1.7 0 0 0-.34 1.88 1.7 1.7 0 0 0 1.56 1.03h.7v3.1h-.7a1.7 1.7 0 0 0-1.56 1.03z" />
    </svg>
  );
}

export function PlusIcon() {
  return (
    <svg viewBox="0 0 24 24" width="16" height="16" aria-hidden="true" {...common}>
      <path d="M12 5v14M5 12h14" />
    </svg>
  );
}

export function SunIcon() {
  return (
    <svg viewBox="0 0 24 24" width="17" height="17" aria-hidden="true" {...common}>
      <circle cx="12" cy="12" r="4" />
      <path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" />
    </svg>
  );
}

export function MoonIcon() {
  return (
    <svg viewBox="0 0 24 24" width="17" height="17" aria-hidden="true" {...common}>
      <path d="M20 14.5A8 8 0 0 1 9.5 4 8.5 8.5 0 1 0 20 14.5z" />
    </svg>
  );
}

export function MonitorIcon() {
  return (
    <svg viewBox="0 0 24 24" width="17" height="17" aria-hidden="true" {...common}>
      <rect x="3" y="4" width="18" height="12" rx="1.6" />
      <path d="M8 20h8M12 16v4" />
    </svg>
  );
}

export function LoansIcon() {
  return (
    <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true" {...common}>
      <path d="M3 7h18v10H3z" />
      <path d="M7 12h4M15 10.5v3" />
    </svg>
  );
}

export function SavingsIcon() {
  return (
    <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true" {...common}>
      <path d="M4 12a8 8 0 0 1 16 0v5a2 2 0 0 1-2 2h-3l-2-2H8l-2 2H5a1 1 0 0 1-1-1z" />
      <path d="M9 10h.01M15 10h.01M12 7v1" />
    </svg>
  );
}

export function ObligationsIcon() {
  return (
    <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true" {...common}>
      <path d="M6 3h9l4 4v14H6z" />
      <path d="M9 12h7M9 16h5M9 8h3" />
    </svg>
  );
}
