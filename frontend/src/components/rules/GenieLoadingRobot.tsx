/** Small animated robot shown while Databricks Genie processes a rule request. */
export function GenieLoadingRobot() {
  return (
    <div className="genie-robot" aria-hidden="true">
      <svg
        className="genie-robot__svg"
        viewBox="0 0 80 96"
        width="80"
        height="96"
        fill="none"
        xmlns="http://www.w3.org/2000/svg"
      >
        <g className="genie-robot__body-group">
          <rect
            className="genie-robot__antenna"
            x="38"
            y="4"
            width="4"
            height="10"
            rx="2"
            fill="var(--rd-accent)"
          />
          <circle className="genie-robot__antenna-tip" cx="40" cy="4" r="4" fill="var(--rd-teal)" />
          <rect
            x="14"
            y="18"
            width="52"
            height="44"
            rx="10"
            fill="var(--rd-cream)"
            stroke="var(--rd-accent)"
            strokeWidth="2.5"
          />
          <rect x="22" y="28" width="12" height="12" rx="3" fill="var(--rd-accent)" className="genie-robot__eye genie-robot__eye--left" />
          <rect x="46" y="28" width="12" height="12" rx="3" fill="var(--rd-accent)" className="genie-robot__eye genie-robot__eye--right" />
          <rect x="26" y="32" width="4" height="4" rx="1" fill="var(--rd-accent-bright)" className="genie-robot__pupil genie-robot__pupil--left" />
          <rect x="50" y="32" width="4" height="4" rx="1" fill="var(--rd-accent-bright)" className="genie-robot__pupil genie-robot__pupil--right" />
          <rect x="30" y="48" width="20" height="4" rx="2" fill="var(--rd-primary-light)" />
        </g>
        <rect
          className="genie-robot__arm genie-robot__arm--left"
          x="4"
          y="32"
          width="10"
          height="24"
          rx="5"
          fill="var(--rd-accent-mid)"
        />
        <rect
          className="genie-robot__arm genie-robot__arm--right"
          x="66"
          y="32"
          width="10"
          height="24"
          rx="5"
          fill="var(--rd-accent-mid)"
        />
        <g className="genie-robot__legs">
          <rect x="22" y="64" width="14" height="18" rx="6" fill="var(--rd-accent)" />
          <rect x="44" y="64" width="14" height="18" rx="6" fill="var(--rd-accent)" />
        </g>
        <circle className="genie-robot__spark genie-robot__spark--1" cx="68" cy="22" r="2" fill="var(--rd-gold)" />
        <circle className="genie-robot__spark genie-robot__spark--2" cx="12" cy="26" r="1.5" fill="var(--rd-teal)" />
        <circle className="genie-robot__spark genie-robot__spark--3" cx="72" cy="50" r="1.5" fill="var(--rd-accent-bright)" />
      </svg>
    </div>
  );
}
