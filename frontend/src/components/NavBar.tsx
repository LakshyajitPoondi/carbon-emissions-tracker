import { NavLink, useNavigate } from "react-router-dom";
import { useAppState } from "../context/AppStateContext";
import { useAuth } from "../context/AuthContext";

function navLinkClass({ isActive }: { isActive: boolean }): string {
  return isActive ? "app-nav__link app-nav__link--active" : "app-nav__link";
}

export function NavBar() {
  const { organization, facility } = useAppState();
  const { isAuthenticated, email, logout } = useAuth();
  const navigate = useNavigate();

  function handleLogout() {
    logout();
    navigate("/login", { replace: true });
  }

  return (
    <header className="app-header">
      <div className="app-header__top">
        <span className="app-header__brand">Carbon Emissions Tracker</span>
        {isAuthenticated && (
          <div className="app-header__selection" aria-live="polite">
            <span>{organization ? organization.name : "No organization selected"}</span>
            {organization && (
              <>
                <span aria-hidden="true"> / </span>
                <span>{facility ? facility.name : "No facility selected"}</span>
              </>
            )}
          </div>
        )}
        <div className="app-header__auth">
          {isAuthenticated ? (
            <>
              <span className="app-header__email">{email}</span>
              <button type="button" className="app-header__logout" onClick={handleLogout}>
                Log out
              </button>
            </>
          ) : (
            <NavLink to="/login" className="app-nav__link">
              Sign in
            </NavLink>
          )}
        </div>
      </div>
      {isAuthenticated && (
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
          <NavLink to="/overview" className={navLinkClass}>
            Overview
          </NavLink>
          <NavLink to="/products" className={navLinkClass}>
            Products
          </NavLink>
          <NavLink to="/reports" className={navLinkClass}>
            Reports
          </NavLink>
        </nav>
      )}
    </header>
  );
}
