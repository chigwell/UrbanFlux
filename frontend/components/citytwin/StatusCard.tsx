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
    <CollapsiblePanel title="Planning engine" meta="Live" defaultOpen={true}>
      <div className="flex flex-col gap-3">
        <div className="flex items-center justify-between gap-2 text-sm">
          <span className="flex items-center gap-2 text-muted-foreground">
            <span className="relative flex size-2">
              <span className="absolute inline-flex size-full animate-ping rounded-full bg-green-600 dark:bg-green-400 opacity-60" />
              <span className="relative inline-flex size-2 rounded-full bg-green-600 dark:bg-green-400" />
            </span>
            Live engine
          </span>
          <span className="tabular-nums text-muted-foreground">
            {progress}%
          </span>
        </div>
        <Progress value={progress} />
        <p className="text-sm leading-relaxed text-muted-foreground">
          {status}
        </p>
        <div className="flex flex-wrap gap-2">
          <Badge variant="secondary">
            {pills.roads.toLocaleString()} OSM roads
          </Badge>
          <Badge variant="secondary">
            {pills.water.toLocaleString()} water masks
          </Badge>
          <Badge variant="secondary">
            {pills.anchors.toLocaleString()} anchors
          </Badge>
        </div>
      </div>
    </CollapsiblePanel>
  );
}
