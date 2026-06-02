import { NavLink } from "react-router-dom";

const navItems = [
  { to: "/profile", label: "Profile" },
  { to: "/my-garden", label: "My Garden" },
  { to: "/garden-rules", label: "Garden rules" },
] as const;

export function SideNav() {
  return (
    <nav className="side-nav" aria-label="Main navigation">
      <ul className="side-nav__list">
        {navItems.map(({ to, label }) => (
          <li key={to}>
            <NavLink
              to={to}
              className={({ isActive }) =>
                `side-nav__link${isActive ? " side-nav__link--active" : ""}`
              }
            >
              {label}
            </NavLink>
          </li>
        ))}
      </ul>
    </nav>
  );
}
