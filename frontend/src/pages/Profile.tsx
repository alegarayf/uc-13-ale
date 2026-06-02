import { useState } from "react";
import { CURRENT_USER } from "../constants/user";

const defaultPreferences = {
  emailDigest: true,
  portfolioUpdates: true,
  rallydayReminders: false,
  weeklySummary: true,
} as const;

export function Profile() {
  const [prefs, setPrefs] = useState(defaultPreferences);

  const toggle = (key: keyof typeof defaultPreferences) => {
    setPrefs((prev) => ({ ...prev, [key]: !prev[key] }));
  };

  return (
    <div className="page">
      <header className="page__header">
        <h1 className="page__title">Profile</h1>
        <p className="page__subtitle">Manage your account and notification preferences.</p>
      </header>

      <section className="content-card" aria-labelledby="account-heading">
        <h2 id="account-heading" className="content-card__title">
          Account
        </h2>
        <dl className="detail-list">
          <div className="detail-list__row">
            <dt>Name</dt>
            <dd>{CURRENT_USER.displayName}</dd>
          </div>
          <div className="detail-list__row">
            <dt>Email</dt>
            <dd>{CURRENT_USER.email}</dd>
          </div>
        </dl>
      </section>

      <section className="content-card" aria-labelledby="notifications-heading">
        <h2 id="notifications-heading" className="content-card__title">
          Notification preferences
        </h2>
        <p className="content-card__note">
          Changes are saved locally for now. Backend integration coming later.
        </p>
        <ul className="pref-list">
          {(
            [
              ["emailDigest", "Email digest", "Daily summary of activity in your workspace"],
              ["portfolioUpdates", "Portfolio updates", "Alerts when portfolio company data changes"],
              ["rallydayReminders", "Rallyday reminders", "Reminders before scheduled Rallydays"],
              ["weeklySummary", "Weekly summary", "End-of-week recap delivered on Fridays"],
            ] as const
          ).map(([key, label, description]) => (
            <li key={key} className="pref-list__item">
              <label className="pref-toggle">
                <input
                  type="checkbox"
                  checked={prefs[key]}
                  onChange={() => toggle(key)}
                />
                <span className="pref-toggle__text">
                  <span className="pref-toggle__label">{label}</span>
                  <span className="pref-toggle__desc">{description}</span>
                </span>
              </label>
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}
