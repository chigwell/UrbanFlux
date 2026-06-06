"use client";

import type { CityTwinImpact, CityTwinMetrics } from "@/lib/cityTwinMap";
import { AnalyticsScreen } from "./AnalyticsScreen";

interface DashboardCardProps {
  scenario: string;
  metrics: CityTwinMetrics | null;
  impact: CityTwinImpact | null;
  report: string;
  /** Unique per mount - passed through to the analytics screen's morph. */
  layoutId: string;
}

// The dashboard card is the expandable analytics trigger. The full metric
// content lives in AnalyticsScreen so desktop and mobile share one surface.
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
