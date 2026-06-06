import Link from "next/link";
import { ArrowRightIcon, MapPinnedIcon } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { HeroMap } from "./HeroMap";

export function Hero() {
  return (
    <section className="mx-auto grid w-full max-w-6xl items-center gap-10 px-6 py-16 lg:grid-cols-2 lg:py-24">
      <div className="flex flex-col items-start gap-6">
        <Badge variant="secondary" className="gap-1.5">
          <MapPinnedIcon className="size-3.5" />
          Live London CityTwin
        </Badge>
        <h1 className="text-4xl font-semibold tracking-tight text-balance sm:text-5xl lg:text-6xl">
          Draw a zone. Watch a city plan itself.
        </h1>
        <p className="max-w-prose text-lg text-muted-foreground text-pretty">
          UrbanFlux turns any boundary you draw over London into a water-aware
          regeneration plan — roads snapped to real OpenStreetMap geometry,
          generated buildings, green space, and live impact metrics.
        </p>
        <div className="flex flex-wrap items-center gap-3">
          <Button asChild size="lg">
            <Link href="/app">
              Launch the tool
              <ArrowRightIcon data-icon="inline-end" />
            </Link>
          </Button>
          <Button asChild size="lg" variant="outline">
            <a href="#how">See how it works</a>
          </Button>
        </div>
        <dl className="flex flex-wrap gap-x-8 gap-y-3 pt-4 text-sm">
          <div>
            <dt className="text-muted-foreground">Data source</dt>
            <dd className="font-medium">Live OSM + vector tiles</dd>
          </div>
          <div>
            <dt className="text-muted-foreground">Runs</dt>
            <dd className="font-medium">Entirely in your browser</dd>
          </div>
          <div>
            <dt className="text-muted-foreground">Replans in</dt>
            <dd className="font-medium">Real time</dd>
          </div>
        </dl>
      </div>

      <div className="relative aspect-[4/3] overflow-hidden rounded-2xl border shadow-2xl lg:aspect-square">
        <HeroMap />
        <div className="absolute bottom-4 left-4 rounded-xl border bg-card/85 px-4 py-3 backdrop-blur">
          <p className="text-xs text-muted-foreground">Generated scenario</p>
          <p className="text-lg font-semibold tabular-nums">1,240 homes · 4.2 ha green</p>
        </div>
      </div>
    </section>
  );
}
