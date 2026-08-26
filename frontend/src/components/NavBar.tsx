import { NavLink } from "react-router-dom";
import { useAppState } from "../context/AppStateContext";

function navLinkClass({ isActive }: { isActive: boolean }): string {
  return isActive ? "app-nav__link app-nav__link--active" : "app-nav__link";
}

export function NavBar() {
  const { organization, facility } = useAppState();

  return (
    <header className="app-header">
      <div className="app-header__top">
        <span className="app-header__brand">Carbon Emissions Tracker</span>
        <div className="app-header__selection" aria-live="polite">
          <span>{organization ? organization.name : "No organization selected"}</span>
          {organization && (
            <>
              <span aria-hidden="true"> / </span>
              <span>{facility ? facility.name : "No facility selected"}</span>
            </>
          )}
        </div>
      </div>
      <nav className="app-nav" aria-label="Main">
        <NavLink to="/" end className={navLinkClass}>
          Setup
        </NavLink>
        <NavLink to="/consumption" className={navLinkClass}>
          Consumption
        </NavLink>
        <NavLink to="/dashboard" className={navLinkClass}>
          Dashboard
        </NavLink>
        <NavLink to="/reports" className={navLinkClass}>
          Reports
        </NavLink>
      </nav>
    </header>
  );
}
