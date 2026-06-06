import Link from "next/link";
import { ArrowRightIcon, StarIcon } from "lucide-react";
import { Button } from "@/components/ui/button";
import { HeroMap } from "./HeroMap";

export function Hero() {
  return (
    <section className="relative flex min-h-[calc(100dvh-4rem)] flex-col items-center overflow-hidden px-6 pt-16 sm:pt-20">
      <div
        className="uf-enter flex max-w-3xl flex-col items-center text-center"
        style={{ animationDelay: "40ms" }}
      >
        <h1 className="mt-7 text-5xl font-semibold leading-[0.95] tracking-tighter text-balance sm:text-6xl lg:text-7xl">
          Redraw a city block,
          <span className="uf-accent-text block">watch it replan itself.</span>
        </h1>

        <p className="mt-6 max-w-xl text-lg leading-8 text-muted-foreground text-pretty">
          Draw any boundary over London and UrbanFlux generates a water-aware
          regeneration plan — roads, buildings, green space and live impact
          metrics. Entirely in your browser.
        </p>

        <div className="mt-8 flex flex-wrap items-center justify-center gap-3">
          <Button
            asChild
            size="lg"
            className="h-11 rounded-none p-4 shadow-lg shadow-primary/20"
          >
            <Link href="/app">
              Launch the tool
              <ArrowRightIcon data-icon="inline-end" />
            </Link>
          </Button>
          <Button
            asChild
            size="lg"
            variant="outline"
            className="h-11 rounded-none p-4 bg-background/50 backdrop-blur"
          >
            <a href="https://github.com/chigwell/UrbanFlux">
              <StarIcon data-icon="inline-start" />
              Star on GitHub
            </a>
          </Button>
        </div>
      </div>
      <div
        className="uf-enter relative mt-14 w-full max-w-5xl"
        style={{ animationDelay: "160ms" }}
      >
        <div className="pointer-events-none absolute -inset-x-10 -top-16 bottom-0 bg-[radial-gradient(60%_60%_at_50%_0%,color-mix(in_oklch,var(--uf-accent)_28%,transparent),transparent_70%)] blur-2xl" />
        <div className="uf-map-frame relative aspect-16/10 overflow-hidden rounded-t-[1.75rem] border border-foreground/10 bg-card/40 sm:aspect-video">
          <HeroMap />
          <div className="pointer-events-none absolute inset-3 rounded-[1.35rem] border border-white/10" />

          <div className="absolute left-4 top-4 flex items-center gap-2 rounded-full border border-white/15 bg-black/35 px-3 py-1.5 text-xs font-medium text-white shadow-sm backdrop-blur">
            <span className="relative flex size-2">
              <span className="absolute inline-flex size-full animate-ping rounded-full bg-emerald-400 opacity-70" />
              <span className="relative inline-flex size-2 rounded-full bg-emerald-400" />
            </span>
            Planning engine live
          </div>

          <div className="uf-float uf-glass absolute bottom-5 left-5 rounded-2xl p-4">
            <p className="text-xs uppercase tracking-widest text-muted-foreground">
              Generated scenario
            </p>
            <div className="mt-1.5 flex items-end gap-3">
              <p className="text-2xl font-semibold tracking-tight tabular-nums">
                1,240
              </p>
              <p className="pb-0.5 text-sm text-muted-foreground">
                homes · 4.2 ha green
              </p>
            </div>
          </div>
        </div>
        <div className="pointer-events-none absolute inset-x-0 bottom-0 h-24 bg-linear-to-t from-background to-transparent" />
      </div>
    </section>
  );
}
