"use client";

import type {
  CityTwinImpact,
  CityTwinImpactMetric,
  CityTwinMetrics,
} from "@/lib/cityTwinMap";
import { cn } from "@/lib/utils";
import { CollapsiblePanel } from "./CollapsiblePanel";

interface DashboardCardProps {
  scenario: string;
  metrics: CityTwinMetrics | null;
  impact: CityTwinImpact | null;
  report: string;
}

const DASH = "—";

export function DashboardCard({
  scenario,
  metrics,
  impact,
  report,
}: DashboardCardProps) {
  const tiles: { label: string; value: string }[] = [
    { label: "Area", value: metrics ? `${metrics.area} ha` : DASH },
    { label: "Homes", value: metrics?.homes ?? DASH },
    { label: "Road links", value: metrics?.links ?? DASH },
    { label: "Water protected", value: metrics?.water ?? DASH },
    { label: "Buildings", value: metrics?.buildings ?? DASH },
    { label: "Parking", value: metrics?.parking ?? DASH },
  ];

  return (
    <CollapsiblePanel title="Impact dashboard" meta={scenario}>
      <div className="flex flex-col gap-4">
        <p className="text-sm leading-relaxed text-muted-foreground">
          {report}
        </p>
        <div className="grid grid-cols-2 gap-2">
          {tiles.map((tile) => (
            <div key={tile.label} className=" border-[0.5px] bg-muted/30 p-3">
              <span className="text-xs text-muted-foreground">
                {tile.label}
              </span>
              <span className="mt-1 block text-base font-medium tabular-nums">
                {tile.value}
              </span>
            </div>
          ))}
        </div>
        <ImpactMetrics impact={impact} />
      </div>
    </CollapsiblePanel>
  );
}

// Tint each metric green/red by the sign of its delta. The delta consistently
// leads with +/- (the value sometimes omits it, e.g. "0.19 lives/year").
function metricSign(
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

function ImpactMetrics({ impact }: { impact: CityTwinImpact | null }) {
  const message =
    !impact || impact.status === "ready"
      ? null
      : impact.status === "loading"
        ? "Estimating impact…"
        : "Impact estimate unavailable. Adjust the controls to try again.";

  return (
    <div className="flex flex-col gap-2">
      <span className="text-xs font-medium text-muted-foreground">
        Impact metrics
      </span>
      {message ? (
        <p className="text-sm text-muted-foreground">{message}</p>
      ) : impact?.status === "ready" && impact.metrics?.length ? (
        <>
          <div className="flex flex-col gap-2">
            {impact.metrics.map((metric) => {
              const sign = metricSign(metric);
              return (
                <div
                  key={metric.metric}
                  className={cn(
                    "border-[0.5px] p-3",
                    sign === "positive" &&
                      "border-emerald-500/30 bg-emerald-500/10",
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
                    {metric.source ? (
                      <a
                        href={metric.source}
                        target="_blank"
                        rel="noreferrer"
                        className="text-xs underline underline-offset-2 hover:text-foreground"
                      >
                        Source
                      </a>
                    ) : null}
                  </div>
                </div>
              );
            })}
          </div>
          {/* {impact.note ? (
            <p className="text-xs text-muted-foreground">{impact.note}</p>
          ) : null} */}
        </>
      ) : (
        <p className="text-sm text-muted-foreground">
          Adjust the controls to estimate impact.
        </p>
      )}
    </div>
  );
}
