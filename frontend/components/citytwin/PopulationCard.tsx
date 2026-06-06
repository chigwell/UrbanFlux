"use client";

import type { CityTwinPopulation } from "@/lib/cityTwinMap";
import { CollapsiblePanel } from "./CollapsiblePanel";

interface PopulationCardProps {
  population: CityTwinPopulation | null;
  heightAmbition: number;
}

const BASELINE_HEIGHT_AMBITION = 58;
const SKYSCRAPER_THRESHOLD = 88;

function parsePopulation(value: string | undefined): number | null {
  if (!value) {
    return null;
  }

  const parsed = Number(value.replace(/[^\d.-]/g, ""));
  return Number.isFinite(parsed) ? parsed : null;
}

function heightPopulationMultiplier(heightAmbition: number): number {
  const height = Math.max(0, Math.min(100, heightAmbition));

  if (height <= SKYSCRAPER_THRESHOLD) {
    return Math.max(0.55, 1 + (height - BASELINE_HEIGHT_AMBITION) * 0.012);
  }

  const preSkyscraperMultiplier =
    1 + (SKYSCRAPER_THRESHOLD - BASELINE_HEIGHT_AMBITION) * 0.012;
  const skyscraperShare =
    (height - SKYSCRAPER_THRESHOLD) / (100 - SKYSCRAPER_THRESHOLD);

  return preSkyscraperMultiplier + Math.pow(skyscraperShare, 1.7) * 1.6;
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

export function PopulationCard({
  population,
  heightAmbition,
}: PopulationCardProps) {
  const currentPopulation =
    population?.status === "ready"
      ? population.approximatePopulation ?? parsePopulation(population.population)
      : null;
  const projectedPopulation =
    currentPopulation == null
      ? null
      : Math.round(currentPopulation * heightPopulationMultiplier(heightAmbition));
  const populationDelta =
    currentPopulation != null && projectedPopulation != null
      ? projectedPopulation - currentPopulation
      : null;
  const deltaLabel =
    populationDelta == null
      ? null
      : `${populationDelta >= 0 ? "+" : ""}${populationDelta.toLocaleString()}`;

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
        <div className="flex flex-col gap-3">
          <div className="grid grid-cols-2 gap-2">
            <div className="border-[0.5px] bg-background/60 p-2">
              <span className="block text-xs text-muted-foreground">
                Current
              </span>
              <div className="flex items-baseline gap-1.5">
                <span className="text-2xl font-semibold tabular-nums">
                  {population.population}
                </span>
                <span className="text-xs text-muted-foreground">people</span>
              </div>
            </div>
            <div className="border-[0.5px] bg-background/60 p-2">
              <span className="block text-xs text-muted-foreground">
                Projected
              </span>
              <div className="flex items-baseline gap-1.5">
                <span className="text-2xl font-semibold tabular-nums">
                  {projectedPopulation?.toLocaleString() ?? "—"}
                </span>
                <span className="text-xs text-muted-foreground">people</span>
              </div>
            </div>
          </div>
          {deltaLabel ? (
            <p className="text-xs text-muted-foreground tabular-nums">
              {deltaLabel} people at height ambition {heightAmbition}
              {heightAmbition > SKYSCRAPER_THRESHOLD ? " · skyscraper mix" : ""}
            </p>
          ) : null}
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
