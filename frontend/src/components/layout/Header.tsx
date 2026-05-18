import { Link } from "react-router-dom";
import { CURRENT_USER } from "../../constants/user";

type HeaderProps = {
  onAuthAction?: () => void;
};

export function Header({ onAuthAction }: HeaderProps) {
  return (
    <header className="app-header">
      <Link to="/" className="app-header__brand" aria-label="Rallyday Partners home">
        <img
          src="/rallypartners-logo.svg"
          alt=""
          className="app-header__logo"
          width={40}
          height={40}
        />
        <span className="app-header__name">Rallyday Partners</span>
      </Link>

      <div className="app-header__user">
        <span className="app-header__user-name">{CURRENT_USER.displayName}</span>
        <button
          type="button"
          className="app-header__auth-btn"
          onClick={onAuthAction}
          aria-label="Log out (placeholder)"
        >
          Log out
        </button>
      </div>
    </header>
  );
}
