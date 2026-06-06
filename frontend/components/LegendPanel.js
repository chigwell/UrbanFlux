const legendItems = [
  {
    swatch: "existing",
    title: "Existing OSM roads",
    text: "Fetched from Overpass where available, with basemap fallback.",
  },
  {
    swatch: "road",
    title: "Snapped new roads",
    text: "Cyan connectors rebuild from boundary anchors and the selected zone.",
  },
  {
    swatch: "green",
    title: "Generated zoning",
    text: "Homes, parks and parking react to every polygon or slider change.",
  },
  {
    swatch: "water",
    title: "Water exclusion",
    text: "Water features are avoided unless the override checkbox is enabled.",
  },
];

export default function LegendPanel() {
  return (
    <details className="panel" id="legendPanel">
      <summary>
        <span className="summary-title">What the demo proves</span>
        <span className="summary-meta">topology</span>
      </summary>
      <div className="panel-body">
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
