const metrics = [
  { label: "Selected area", valueId: "areaMetric", delta: "hectares" },
  { label: "Homes", valueId: "homesMetric", delta: "estimated capacity" },
  { label: "Road links", valueId: "linksMetric", delta: "generated network" },
  { label: "Water protected", valueId: "waterMetric", delta: "inside zone" },
  { label: "Buildings", valueId: "buildingsMetric", delta: "generated footprints" },
  { label: "Parking", valueId: "parkingMetric", delta: "estimated spaces" },
];

export default function DashboardPanel() {
  return (
    <details className="panel" id="dashboardPanel" open>
      <summary>
        <span className="summary-title">Impact dashboard</span>
        <span className="summary-meta" id="scenarioLabel">
          No scenario yet
        </span>
      </summary>
      <div className="panel-body">
        <div className="metric-grid">
          {metrics.map((metric) => (
            <div className="metric" key={metric.valueId}>
              <div className="label">{metric.label}</div>
              <div className="value" id={metric.valueId}>
                -
              </div>
              <div className="delta">{metric.delta}</div>
            </div>
          ))}
        </div>
        <div className="report">
          <p className="report-title">AI planning note</p>
          <p className="report-text" id="reportText">
            Waiting for a valid polygon. Click four or more points, or use the demo zone.
          </p>
        </div>
      </div>
    </details>
  );
}
