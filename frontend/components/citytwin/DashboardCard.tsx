"use client";

import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import type { CityTwinMetrics } from "@/lib/cityTwinMap";

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
    <Card className="gap-4 bg-card/85 backdrop-blur">
      <CardHeader>
        <CardTitle>Impact dashboard</CardTitle>
        <CardDescription>{scenario}</CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        <div className="grid grid-cols-3 gap-2">
          {tiles.map((tile) => (
            <div
              key={tile.label}
              className="flex flex-col gap-1 rounded-lg border bg-background/40 p-2.5"
            >
              <span className="text-xs text-muted-foreground">{tile.label}</span>
              <span className="text-base font-semibold tabular-nums">{tile.value}</span>
            </div>
          ))}
        </div>
        <p className="text-xs leading-relaxed text-muted-foreground">{report}</p>
      </CardContent>
    </Card>
  );
}
