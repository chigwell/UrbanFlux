export default function StatusPanel() {
  return (
    <details className="status-card glass accordion-card status-panel" id="statusPanel">
      <summary>
        <span className="accordion-summary-title">Planning engine</span>
        <span className="accordion-summary-meta">live</span>
      </summary>
      <div className="accordion-body">
        <div className="status-head">
          <span>Planning engine</span>
          <span className="pulse" />
        </div>
        <div className="progress-track">
          <div className="progress-bar" id="progressBar" />
        </div>
        <p className="status-text" id="statusText">
          Ready. The demo zone will load automatically; drag any vertex to regenerate.
        </p>
        <div className="status-pills">
          <span className="pill">
            OSM roads <strong id="roadsPill">-</strong>
          </span>
          <span className="pill">
            Water masks <strong id="waterPill">-</strong>
          </span>
          <span className="pill">
            Anchors <strong id="anchorsPill">-</strong>
          </span>
        </div>
      </div>
    </details>
  );
}
