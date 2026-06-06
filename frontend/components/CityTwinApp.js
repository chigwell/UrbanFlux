"use client";

import { useEffect } from "react";
import { initCityTwinMap } from "../lib/cityTwinMap";
import ControlsPanel from "./ControlsPanel";
import DashboardPanel from "./DashboardPanel";
import IntroPanel from "./IntroPanel";
import LegendPanel from "./LegendPanel";
import StatusPanel from "./StatusPanel";

export default function CityTwinApp() {
  useEffect(() => initCityTwinMap(), []);

  return (
    <>
      <div id="map" />
      <div className="grid-noise" />

      <main className="shell">
        <section className="topbar">
          <IntroPanel />
          <StatusPanel />
        </section>

        <section className="workbench">
          <ControlsPanel />
          <LegendPanel />
          <DashboardPanel />
        </section>

        <div className="map-hint" id="mapHint">
          Click at least four points. Drag cyan vertices. White handles add new points.
        </div>
        <div className="toast" id="toast" />
      </main>
    </>
  );
}
