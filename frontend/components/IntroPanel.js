export default function IntroPanel() {
  return (
    <details className="hero glass accordion-card intro-card" id="introPanel">
      <summary>
        <span className="accordion-summary-title">CityTwin demo</span>
        <span className="accordion-summary-meta">intro</span>
      </summary>
      <div className="accordion-body intro-body">
        <div className="badge-row">
          <span className="badge">NVIDIA Hackathon Concept</span>
          <span className="badge">London Open Data + OSM</span>
          <span className="badge">Live CityTwin</span>
        </div>
        <h1>
          <span className="gradient-text">Draw a zone.</span>
          <br />
          Watch London redesign itself.
        </h1>
        <p className="subtitle">
          Select a 4+ point polygon. The demo fetches nearby road, building, park and water geometry,
          snaps generated streets to real boundary roads, protects water by default and rebuilds the
          neighbourhood as you drag every point.
        </p>
      </div>
    </details>
  );
}
