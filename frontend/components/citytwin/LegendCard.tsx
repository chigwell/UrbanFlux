"use client";

import { CollapsiblePanel } from "./CollapsiblePanel";

const LEGEND: { color: string; label: string; hint: string }[] = [
  { color: "#ffb86b", label: "Existing roads", hint: "OSM / basemap context" },
  {
    color: "#06b6d4",
    label: "Generated roads",
    hint: "Snapped boundary connectors",
  },
  {
    color: "#7dff9f",
    label: "Green & zoning",
    hint: "Parks and generated blocks",
  },
  { color: "#3b82f6", label: "Water exclusion", hint: "Hard masks for rivers" },
];

export function LegendCard() {
  return (
    <CollapsiblePanel title="What the demo proves" meta="Topology">
      <div className="grid grid-cols-2 gap-3">
        {LEGEND.map((item) => (
          <div key={item.label} className="flex min-w-0 items-start gap-2">
            <span
              className="mt-0.5 size-3 shrink-0 rounded-full ring-1 ring-border"
              style={{ backgroundColor: item.color }}
            />
            <div className="flex min-w-0 flex-col">
              <span className="text-xs font-medium leading-tight">
                {item.label}
              </span>
              <span className="text-[11px] leading-tight text-muted-foreground">
                {item.hint}
              </span>
            </div>
          </div>
        ))}
      </div>
    </CollapsiblePanel>
  );
}
