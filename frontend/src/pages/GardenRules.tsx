const mockRules = [
  {
    id: "gr-001",
    name: "Revenue threshold",
    description: "Minimum annual revenue for portfolio consideration.",
    value: "$10M",
    status: "Active",
  },
  {
    id: "gr-002",
    name: "Geography",
    description: "Primary operating region for eligible companies.",
    value: "North America",
    status: "Active",
  },
  {
    id: "gr-003",
    name: "Growth mindset score",
    description: "Minimum qualitative score from partner review.",
    value: "≥ 7 / 10",
    status: "Draft",
  },
  {
    id: "gr-004",
    name: "Differentiation criteria",
    description: "Requires documented secret sauce or moat.",
    value: "Required",
    status: "Active",
  },
] as const;

export function GardenRules() {
  return (
    <div className="page">
      <header className="page__header">
        <h1 className="page__title">Garden rules</h1>
        <p className="page__subtitle">
          Define and manage criteria that shape how opportunities are evaluated.
        </p>
      </header>

      <section className="content-card" aria-labelledby="rules-heading">
        <div className="content-card__toolbar">
          <h2 id="rules-heading" className="content-card__title">
            Active rules
          </h2>
          <button type="button" className="btn btn--primary" disabled title="Coming soon">
            Add rule
          </button>
        </div>
        <p className="content-card__note">
          Placeholder rules — editing and persistence will connect to the API later.
        </p>

        <div className="rules-table-wrap">
          <table className="rules-table">
            <thead>
              <tr>
                <th scope="col">Rule</th>
                <th scope="col">Description</th>
                <th scope="col">Value</th>
                <th scope="col">Status</th>
              </tr>
            </thead>
            <tbody>
              {mockRules.map((rule) => (
                <tr key={rule.id}>
                  <td>
                    <span className="rules-table__name">{rule.name}</span>
                    <span className="rules-table__id">{rule.id}</span>
                  </td>
                  <td>{rule.description}</td>
                  <td>{rule.value}</td>
                  <td>
                    <span
                      className={`rules-table__status rules-table__status--${rule.status.toLowerCase()}`}
                    >
                      {rule.status}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}
