import { useState } from "react";
import type { ReactNode } from "react";
import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { useAppState } from "../context/AppStateContext";
import { useAuth } from "../context/AuthContext";

type IconName =
  | "setup"
  | "consumption"
  | "dashboard"
  | "overview"
  | "products"
  | "reports"
  | "account";

const NAV_SECTIONS: Array<{
  label: string;
  links: Array<{ to: string; label: string; icon: IconName; end?: boolean }>;
}> = [
  {
    label: "Workspace",
    links: [{ to: "/", label: "Setup", icon: "setup", end: true }],
  },
  {
    label: "Tracking",
    links: [
      { to: "/consumption", label: "Consumption", icon: "consumption" },
      { to: "/products", label: "Products", icon: "products" },
    ],
  },
  {
    label: "Insights",
    links: [
      { to: "/dashboard", label: "Dashboard", icon: "dashboard" },
      { to: "/overview", label: "Overview", icon: "overview" },
      { to: "/reports", label: "Reports", icon: "reports" },
    ],
  },
];

function NavIcon({ name }: { name: IconName }) {
  const paths: Record<IconName, ReactNode> = {
    setup: (
      <>
        <path d="M4 7h16M7 4v6M4 17h16M17 14v6" />
      </>
    ),
    consumption: <path d="M12 3S6.5 9.2 6.5 14a5.5 5.5 0 0 0 11 0C17.5 9.2 12 3 12 3Z" />,
    dashboard: (
      <>
        <rect x="4" y="4" width="6" height="6" rx="1" />
        <rect x="14" y="4" width="6" height="6" rx="1" />
        <rect x="4" y="14" width="6" height="6" rx="1" />
        <rect x="14" y="14" width="6" height="6" rx="1" />
      </>
    ),
    overview: (
      <>
        <path d="M4 20V9l8-5 8 5v11" />
        <path d="M9 20v-6h6v6M8 10h.01M12 10h.01M16 10h.01" />
      </>
    ),
    products: (
      <>
        <path d="m12 3 8 4.5v9L12 21l-8-4.5v-9L12 3Z" />
        <path d="m4.5 7.8 7.5 4.3 7.5-4.3M12 12.1V21" />
      </>
    ),
    reports: (
      <>
        <path d="M6 3h9l3 3v15H6V3Z" />
        <path d="M14 3v4h4M9 12h6M9 16h6" />
      </>
    ),
    account: (
      <>
        <path d="M10 5H5v14h5M13 8l4 4-4 4M8 12h9" />
      </>
    ),
  };

  return (
    <svg className="app-sidebar__icon" viewBox="0 0 24 24" aria-hidden="true">
      {paths[name]}
    </svg>
  );
}

function navLinkClass({ isActive }: { isActive: boolean }): string {
  return isActive
    ? "app-sidebar__link app-sidebar__link--active"
    : "app-sidebar__link";
}

export function AppShell() {
  const { organization, facility } = useAppState();
  const { isAuthenticated, email, logout } = useAuth();
  const [mobileNavOpen, setMobileNavOpen] = useState(false);
  const navigate = useNavigate();

  function handleLogout() {
    setMobileNavOpen(false);
    logout();
    navigate("/login", { replace: true });
  }

  function closeMobileNav() {
    setMobileNavOpen(false);
  }

  return (
    <div className="app-shell">
      <header className="app-topbar">
        <div className="app-topbar__brand-group">
          <button
            type="button"
            className="app-topbar__menu"
            aria-controls="app-sidebar"
            aria-expanded={mobileNavOpen}
            aria-label={mobileNavOpen ? "Close navigation" : "Open navigation"}
            onClick={() => setMobileNavOpen((open) => !open)}
          >
            <span aria-hidden="true" />
            <span aria-hidden="true" />
            <span aria-hidden="true" />
          </button>
          <span className="app-topbar__mark" aria-hidden="true">C</span>
          <span className="app-topbar__brand">Carbon Emissions Tracker</span>
        </div>

        {isAuthenticated && (
          <div className="app-topbar__selection" aria-live="polite">
            <span>{organization ? organization.name : "No organization selected"}</span>
            <span className="app-topbar__selection-divider" aria-hidden="true">/</span>
            <span>{facility ? facility.name : "No facility selected"}</span>
          </div>
        )}

        <div className="app-topbar__account">
          {isAuthenticated ? (
            <>
              <span className="app-topbar__email">{email}</span>
              <button type="button" className="app-topbar__logout" onClick={handleLogout}>
                Sign out
              </button>
            </>
          ) : (
            <NavLink to="/login" className="app-topbar__signin">Sign in</NavLink>
          )}
        </div>
      </header>

      <aside
        id="app-sidebar"
        className={`app-sidebar${mobileNavOpen ? " app-sidebar--open" : ""}`}
      >
        {isAuthenticated ? (
          <>
            <nav className="app-sidebar__nav" aria-label="Main navigation">
              <div className="app-sidebar__context" aria-live="polite">
                <strong>{organization ? organization.name : "No organization selected"}</strong>
                <span>{facility ? facility.name : "No facility selected"}</span>
              </div>
              {NAV_SECTIONS.map((section) => (
                <div className="app-sidebar__section" key={section.label}>
                  <span className="app-sidebar__section-label">{section.label}</span>
                  {section.links.map((link) => (
                    <NavLink
                      key={link.to}
                      to={link.to}
                      end={link.end}
                      className={navLinkClass}
                      onClick={closeMobileNav}
                    >
                      <NavIcon name={link.icon} />
                      <span>{link.label}</span>
                    </NavLink>
                  ))}
                </div>
              ))}
            </nav>
            <div className="app-sidebar__account">
              <span className="app-sidebar__section-label">Account</span>
              <button type="button" className="app-sidebar__link" onClick={handleLogout}>
                <NavIcon name="account" />
                <span>Sign out</span>
              </button>
            </div>
          </>
        ) : (
          <nav className="app-sidebar__nav" aria-label="Account navigation">
            <div className="app-sidebar__section">
              <span className="app-sidebar__section-label">Account</span>
              <NavLink
                to="/login"
                className={navLinkClass}
                onClick={closeMobileNav}
              >
                <NavIcon name="account" />
                <span>Sign in</span>
              </NavLink>
            </div>
          </nav>
        )}
      </aside>

      {mobileNavOpen && (
        <button
          type="button"
          className="app-shell__scrim"
          aria-label="Close navigation"
          onClick={closeMobileNav}
        />
      )}

      <div className="app-content">
        <Outlet />
      </div>
    </div>
  );
}
