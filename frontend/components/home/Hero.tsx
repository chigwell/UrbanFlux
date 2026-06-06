import Image from "next/image";
import Link from "next/link";
import { ArrowRightIcon, StarIcon } from "lucide-react";
import { Button } from "@/components/ui/button";

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
          regeneration plan - roads, buildings, green space and live impact
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
        <div className="overflow-hidden rounded-xl border border-foreground/10 bg-card shadow-sm ring-1 ring-foreground/10">
          <Image
            src="/urbanflux-demo.png"
            alt="UrbanFlux CityTwin demo with generated buildings, roads, and planning controls over London"
            width={3456}
            height={1940}
            className="block h-auto w-full"
            priority
            unoptimized
          />
        </div>
        <div className="pointer-events-none absolute inset-x-0 bottom-0 h-16 bg-linear-to-t from-background to-transparent" />
      </div>
    </section>
  );
}
