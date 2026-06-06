"use client";

import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import type { CityTwinPills } from "@/lib/cityTwinMap";
import { CollapsiblePanel } from "./CollapsiblePanel";

interface StatusCardProps {
  progress: number;
  status: string;
  pills: CityTwinPills;
}

export function StatusCard({ progress, status, pills }: StatusCardProps) {
  return (
    <CollapsiblePanel title="Planning engine" meta="live" defaultOpen={true}>
      <div className="flex flex-col gap-3">
        <div className="flex items-center gap-2">
          <span className="relative flex size-2">
            <span className="absolute inline-flex size-full animate-ping rounded-full bg-primary opacity-60" />
            <span className="relative inline-flex size-2 rounded-full bg-primary" />
          </span>
          <span className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            Live engine
          </span>
        </div>
        <Progress value={progress} />
        <p className="text-sm text-muted-foreground">{status}</p>
        <div className="flex flex-wrap gap-2">
          <Badge variant="secondary">{pills.roads.toLocaleString()} OSM roads</Badge>
          <Badge variant="secondary">{pills.water.toLocaleString()} water masks</Badge>
          <Badge variant="secondary">{pills.anchors.toLocaleString()} anchors</Badge>
        </div>
      </div>
    </CollapsiblePanel>
  );
}
