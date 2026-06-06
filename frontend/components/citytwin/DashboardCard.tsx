"use client";

import type { CityTwinImpact, CityTwinMetrics } from "@/lib/cityTwinMap";
import { AnalyticsScreen } from "./AnalyticsScreen";

interface DashboardCardProps {
  scenario: string;
  metrics: CityTwinMetrics | null;
  impact: CityTwinImpact | null;
  report: string;
  /** Unique per mount — passed through to the analytics screen's morph. */
  layoutId: string;
}

// The Impact dashboard is no longer a collapsible panel: its card header is the
// trigger that morphs straight into the full-screen analytics view.
export function DashboardCard({
  scenario,
  metrics,
  impact,
  report,
  layoutId,
}: DashboardCardProps) {
  return (
    <AnalyticsScreen
      scenario={scenario}
      metrics={metrics}
      impact={impact}
      report={report}
      layoutId={layoutId}
    />
  );
}
