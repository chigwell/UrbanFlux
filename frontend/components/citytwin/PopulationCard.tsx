"use client";

import type { CityTwinPopulation } from "@/lib/cityTwinMap";
import { CollapsiblePanel } from "./CollapsiblePanel";

interface PopulationCardProps {
  population: CityTwinPopulation | null;
}

function meta(population: CityTwinPopulation | null): string {
  if (!population) {
    return "—";
  }
  switch (population.status) {
    case "loading":
      return "Estimating…";
    case "error":
      return "Unavailable";
    case "ready":
      return "2021 Census";
  }
}

export function PopulationCard({ population }: PopulationCardProps) {
  return (
    <CollapsiblePanel
      title="Estimated population"
      meta={meta(population)}
      defaultOpen={true}
    >
      {!population ? (
        <p className="text-sm leading-relaxed text-muted-foreground">
          Draw a zone to estimate the population living inside it.
        </p>
      ) : population.status === "loading" ? (
        <p className="text-sm leading-relaxed text-muted-foreground">
          Estimating population for the selected area…
        </p>
      ) : population.status === "error" ? (
        <p className="text-sm leading-relaxed text-muted-foreground">
          Population estimate is unavailable right now. Reshape the zone to try
          again.
        </p>
      ) : (
        <div className="flex flex-col gap-1.5">
          <div className="flex items-baseline gap-2">
            <span className="text-3xl font-semibold tabular-nums">
              {population.population}
            </span>
            <span className="text-sm text-muted-foreground">people</span>
          </div>
          {population.lsoaCount != null && population.areaKm2 != null ? (
            <p className="text-xs text-muted-foreground tabular-nums">
              {population.lsoaCount.toLocaleString()} LSOA
              {population.lsoaCount === 1 ? "" : "s"} · {population.areaKm2} km²
            </p>
          ) : null}
          {population.note ? (
            <p className="text-xs text-muted-foreground">{population.note}</p>
          ) : null}
        </div>
      )}
    </CollapsiblePanel>
  );
}
