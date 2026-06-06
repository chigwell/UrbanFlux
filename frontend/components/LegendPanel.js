const legendItems = [
  {
    swatch: "existing",
    title: "Existing OSM roads",
    text: "Fetched as real LineStrings, not guessed from a raster tile.",
  },
  {
    swatch: "road",
    title: "Snapped new roads",
    text: "Cyan connectors start on existing roads and pass through boundary anchors.",
  },
  {
    swatch: "green",
    title: "Generated zoning",
    text: "Homes, parks and parking rebuild on every polygon or slider change.",
  },
  {
    swatch: "water",
    title: "Water exclusion",
    text: "Rivers and water bodies are protected unless the checkbox is enabled.",
  },
];

export default function LegendPanel() {
  return (
    <details className="legend panel glass accordion-card" id="legendPanel">
      <summary>
        <span className="accordion-summary-title">What the demo proves</span>
        <span className="accordion-summary-meta">topology</span>
      </summary>
      <div className="accordion-body">
        <div className="legend-grid">
          {legendItems.map((item) => (
            <div className="legend-card" key={item.swatch}>
              <div className={`swatch ${item.swatch}`} />
              <strong>{item.title}</strong>
              <span>{item.text}</span>
            </div>
          ))}
        </div>
      </div>
    </details>
  );
}
