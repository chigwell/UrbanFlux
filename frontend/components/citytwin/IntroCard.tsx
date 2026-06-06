"use client";

import { Badge } from "@/components/ui/badge";
import { CollapsiblePanel } from "./CollapsiblePanel";

export function IntroCard() {
  return (
    <CollapsiblePanel title="CityTwin demo" meta="intro">
      <div className="flex flex-wrap gap-2">
        <Badge variant="secondary">NVIDIA Hackathon Concept</Badge>
        <Badge variant="secondary">OSM + OpenFreeMap</Badge>
        <Badge variant="secondary">Live CityTwin</Badge>
      </div>
      <h1 className="mt-3 font-heading text-2xl font-semibold leading-tight tracking-tight sm:text-3xl">
        <span className="bg-gradient-to-r from-primary to-cyan-400 bg-clip-text text-transparent">
          Draw a zone.
        </span>
        <br />
        Watch London redesign itself.
      </h1>
      <p className="mt-3 text-sm leading-relaxed text-muted-foreground">
        Select a 4+ point polygon. The demo reads nearby roads, buildings, parks and water,
        protects water by default and rebuilds the neighbourhood as you drag points or tune
        sliders.
      </p>
    </CollapsiblePanel>
  );
}
