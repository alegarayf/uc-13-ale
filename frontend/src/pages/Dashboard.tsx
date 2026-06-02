import { CURRENT_USER } from "../constants/user";

const mockStats = [
  { label: "Active initiatives", value: "12", trend: "+2 this quarter" },
  { label: "Portfolio companies", value: "8", trend: "On track" },
  { label: "Team members", value: "24", trend: "3 new hires" },
  { label: "Upcoming Rallydays", value: "4", trend: "Next: May 28" },
] as const;

const mockActivity = [
  { id: 1, title: "Q2 planning review", date: "May 16, 2026", status: "Completed" },
  { id: 2, title: "Portfolio sync — Acme Co.", date: "May 15, 2026", status: "In progress" },
  { id: 3, title: "Garden rules updated", date: "May 12, 2026", status: "Completed" },
  { id: 4, title: "Notification preferences", date: "May 10, 2026", status: "Pending" },
] as const;

export function Dashboard() {
  return (
    <div className="page">
      <header className="page__header">
        <h1 className="page__title">Dashboard</h1>
        <p className="page__subtitle">
          Welcome back, {CURRENT_USER.displayName.split(" ")[0]}. Here is a snapshot of
          your workspace.
        </p>
      </header>

      <section className="dashboard-stats" aria-label="Summary metrics">
        {mockStats.map((stat) => (
          <article key={stat.label} className="stat-card">
            <p className="stat-card__label">{stat.label}</p>
            <p className="stat-card__value">{stat.value}</p>
            <p className="stat-card__trend">{stat.trend}</p>
          </article>
        ))}
      </section>

      <section className="dashboard-panel" aria-labelledby="recent-activity-heading">
        <h2 id="recent-activity-heading" className="dashboard-panel__title">
          Recent activity
        </h2>
        <p className="dashboard-panel__note">
          Placeholder data — dashboard requirements will be defined later.
        </p>
        <ul className="activity-list">
          {mockActivity.map((item) => (
            <li key={item.id} className="activity-list__item">
              <div className="activity-list__main">
                <span className="activity-list__title">{item.title}</span>
                <span className="activity-list__date">{item.date}</span>
              </div>
              <span className={`activity-list__status activity-list__status--${item.status.toLowerCase().replace(/\s+/g, "-")}`}>
                {item.status}
              </span>
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}
