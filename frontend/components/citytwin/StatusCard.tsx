"use client";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import type { CityTwinPills } from "@/lib/cityTwinMap";

interface StatusCardProps {
  progress: number;
  status: string;
  pills: CityTwinPills;
}

export function StatusCard({ progress, status, pills }: StatusCardProps) {
  return (
    <Card className="gap-3 bg-card/85 py-4 backdrop-blur">
      <CardContent className="flex flex-col gap-3">
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
      </CardContent>
    </Card>
  );
}
