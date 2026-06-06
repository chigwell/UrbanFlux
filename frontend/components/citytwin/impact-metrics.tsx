"use client";

import type {
  CityTwinImpact,
  CityTwinImpactMetric,
  CityTwinMetrics,
} from "@/lib/cityTwinMap";
import { cn } from "@/lib/utils";

const DASH = "—";

/** The six basic scenario tiles shared between the card and the analytics screen. */
export function metricTiles(
  metrics: CityTwinMetrics | null,
): { label: string; value: string }[] {
  return [
    { label: "Area", value: metrics ? `${metrics.area} ha` : DASH },
    { label: "Homes", value: metrics?.homes ?? DASH },
    { label: "Road links", value: metrics?.links ?? DASH },
    { label: "Water protected", value: metrics?.water ?? DASH },
    { label: "Buildings", value: metrics?.buildings ?? DASH },
    { label: "Parking", value: metrics?.parking ?? DASH },
  ];
}

export function MetricTiles({
  metrics,
  className,
}: {
  metrics: CityTwinMetrics | null;
  className?: string;
}) {
  return (
    <div className={cn("grid grid-cols-2 gap-2", className)}>
      {metricTiles(metrics).map((tile) => (
        <div key={tile.label} className="border-[0.5px] bg-muted/30 p-3">
          <span className="text-xs text-muted-foreground">{tile.label}</span>
          <span className="mt-1 block text-base font-medium tabular-nums">
            {tile.value}
          </span>
        </div>
      ))}
    </div>
  );
}

// Tint each metric green/red by the sign of its delta. The delta consistently
// leads with +/- (the value sometimes omits it, e.g. "0.19 lives/year").
export function metricSign(
  metric: CityTwinImpactMetric,
): "positive" | "negative" | "neutral" {
  const text = (metric.delta || metric.value || "").trim();
  if (text.startsWith("+")) {
    return "positive";
  }
  if (text.startsWith("-") || text.startsWith("−")) {
    return "negative";
  }
  return "neutral";
}

/** Pull the first signed number out of a display string for charting. */
export function parseMetricNumber(metric: CityTwinImpactMetric): number {
  const match = (metric.value || metric.delta || "").match(
    /[-+−]?\d+(?:\.\d+)?/,
  );
  if (!match) {
    return 0;
  }
  return Number.parseFloat(match[0].replace("−", "-"));
}

/** Status message for the impact block, or `null` when metrics are ready to show. */
export function impactMessage(impact: CityTwinImpact | null): string | null {
  if (!impact || impact.status === "ready") {
    return null;
  }
  return impact.status === "loading"
    ? "Estimating impact…"
    : "Impact estimate unavailable. Adjust the controls to try again.";
}

export function ImpactMetricCards({
  impact,
  className,
}: {
  impact: CityTwinImpact | null;
  className?: string;
}) {
  const message = impactMessage(impact);

  if (message) {
    return <p className="text-sm text-muted-foreground">{message}</p>;
  }

  if (!(impact?.status === "ready" && impact.metrics?.length)) {
    return (
      <p className="text-sm text-muted-foreground">
        Adjust the controls to estimate impact.
      </p>
    );
  }

  return (
    <div className={cn("flex flex-col gap-2", className)}>
      {impact.metrics.map((metric) => {
        const sign = metricSign(metric);
        return (
          <div
            key={metric.metric}
            className={cn(
              "border-[0.5px] p-3",
              sign === "positive" && "border-emerald-500/30 bg-emerald-500/10",
              sign === "negative" && "border-red-500/30 bg-red-500/10",
              sign === "neutral" && "bg-muted/30",
            )}
          >
            <div className="flex items-baseline justify-between gap-2">
              <span className="text-xs text-muted-foreground">
                {metric.metric}
              </span>
              <span
                className={cn(
                  "text-sm font-medium tabular-nums",
                  sign === "positive" &&
                    "text-emerald-600 dark:text-emerald-400",
                  sign === "negative" && "text-red-600 dark:text-red-400",
                )}
              >
                {metric.value}
              </span>
            </div>
            <div className="mt-1 flex items-baseline justify-between gap-2">
              <span className="text-xs text-muted-foreground">
                {metric.delta}
              </span>
              <a
                href={metric.source}
                target="_blank"
                rel="noreferrer"
                className="text-xs underline underline-offset-2 hover:text-foreground"
              >
                Source
              </a>
            </div>
          </div>
        );
      })}
    </div>
  );
}
