"use client";

import type { CityTwinMetrics } from "@/lib/cityTwinMap";
import { CollapsiblePanel } from "./CollapsiblePanel";

interface DashboardCardProps {
  scenario: string;
  metrics: CityTwinMetrics | null;
  report: string;
}

const DASH = "—";

export function DashboardCard({ scenario, metrics, report }: DashboardCardProps) {
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
        <p className="text-sm leading-relaxed text-muted-foreground">{report}</p>
        <div className="grid grid-cols-2 gap-2">
          {tiles.map((tile) => (
            <div
              key={tile.label}
              className=" border-[0.5px] bg-muted/30 p-3"
            >
              <span className="text-xs text-muted-foreground">{tile.label}</span>
              <span className="mt-1 block text-base font-medium tabular-nums">
                {tile.value}
              </span>
            </div>
          ))}
        </div>
      </div>
    </CollapsiblePanel>
  );
}
