export default function IntroPanel() {
  return (
    <details className="panel intro" id="introPanel" open>
      <summary>
        <span className="summary-title">CityTwin demo</span>
        <span className="summary-meta">London</span>
      </summary>
      <div className="panel-body">
        <div className="badges">
          <span className="badge">NVIDIA Hackathon Concept</span>
          <span className="badge">OSM + OpenFreeMap</span>
          <span className="badge">Live CityTwin</span>
        </div>
        <h1>
          <span className="gradient-text">Draw a zone.</span>
          <br />
          Watch London redesign itself.
        </h1>
        <p className="subtitle">
          Select a 4+ point polygon. The demo reads nearby roads, buildings, parks and water,
          protects water by default and rebuilds the neighbourhood as you drag points or tune sliders.
        </p>
      </div>
    </details>
  );
}
