"use client";

import { Badge } from "@/components/ui/badge";
import { CollapsiblePanel } from "./CollapsiblePanel";

export function IntroCard() {
  return (
    <CollapsiblePanel title="CityTwin demo" meta="Intro">
      <h2 className="text-2xl font-semibold leading-snug tracking-tight">
        Draw a zone. Watch London redesign itself.
      </h2>
      <p className="mt-2 text-sm leading-relaxed text-muted-foreground">
        Select a 4+ point polygon. The demo reads nearby roads, buildings, parks
        and water, protects water by default and rebuilds the neighbourhood as
        you drag points or tune sliders.
      </p>
    </CollapsiblePanel>
  );
}
