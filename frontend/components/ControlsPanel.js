const sliders = [
  { id: "density", label: "Housing density", min: 5, max: 100, value: 64 },
  { id: "green", label: "Green space target", min: 5, max: 80, value: 35 },
  { id: "parking", label: "Parking pressure", min: 0, max: 80, value: 18 },
  { id: "street", label: "Road fill", min: 0, max: 100, value: 35 },
  { id: "alignment", label: "Road alignment", min: 0, max: 100, value: 72 },
  { id: "height", label: "Height ambition", min: 0, max: 100, value: 58 },
];

export default function ControlsPanel() {
  return (
    <details className="controls panel glass accordion-card" id="controlsPanel">
      <summary>
        <span className="accordion-summary-title">Urban controls</span>
        <span className="accordion-summary-meta">closed</span>
      </summary>
      <div className="accordion-body">
        <div className="button-row">
          <button className="btn primary" id="demoButton" type="button">
            Demo
          </button>
          <button className="btn" id="undoButton" type="button">
            Undo
          </button>
          <button className="btn" id="clearButton" type="button">
            Clear
          </button>
          <button className="btn" id="fitButton" type="button">
            Refit
          </button>
        </div>

        <div className="toggles">
          <label className="toggle-line" htmlFor="themeToggle">
            <span>Light theme</span>
            <span className="toggle">
              <input id="themeToggle" type="checkbox" />
              <span className="track">
                <span className="thumb" />
              </span>
            </span>
          </label>

          <label className="toggle-line" htmlFor="allowWaterToggle">
            <span>Water override: allow building over rivers</span>
            <span className="toggle">
              <input id="allowWaterToggle" type="checkbox" />
              <span className="track">
                <span className="thumb" />
              </span>
            </span>
          </label>
        </div>

        <div className="slider-block">
          {sliders.map((slider) => (
            <label className="slider-line" key={slider.id}>
              <span className="slider-label">
                {slider.label} <output id={`${slider.id}Out`}>{slider.value}</output>
              </span>
              <input
                id={slider.id}
                type="range"
                min={slider.min}
                max={slider.max}
                defaultValue={slider.value}
              />
            </label>
          ))}
        </div>
      </div>
    </details>
  );
}
