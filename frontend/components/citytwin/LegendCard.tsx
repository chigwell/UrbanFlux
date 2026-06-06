"use client";

import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";

const LEGEND: { color: string; label: string; hint: string }[] = [
  { color: "#ffb86b", label: "Existing roads", hint: "OSM / basemap context" },
  { color: "#06b6d4", label: "Generated roads", hint: "Snapped boundary connectors" },
  { color: "#7dff9f", label: "Green & zoning", hint: "Parks and generated blocks" },
  { color: "#3b82f6", label: "Water exclusion", hint: "Hard masks for rivers" },
];

export function LegendCard() {
  return (
    <Card className="gap-4 bg-card/85 backdrop-blur">
      <CardHeader>
        <CardTitle>Legend</CardTitle>
      </CardHeader>
      <CardContent className="grid grid-cols-2 gap-x-3 gap-y-3">
        {LEGEND.map((item) => (
          <div key={item.label} className="flex min-w-0 items-start gap-2">
            <span
              className="mt-0.5 size-3.5 shrink-0 rounded-full ring-1 ring-border"
              style={{ backgroundColor: item.color }}
            />
            <div className="flex min-w-0 flex-col">
              <span className="text-xs font-medium leading-tight text-balance">
                {item.label}
              </span>
              <span className="text-[11px] leading-tight text-muted-foreground text-pretty">
                {item.hint}
              </span>
            </div>
          </div>
        ))}
      </CardContent>
    </Card>
  );
}
