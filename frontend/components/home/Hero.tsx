import Image from "next/image";
import Link from "next/link";
import { ArrowRightIcon, StarIcon } from "lucide-react";
import { Button } from "@/components/ui/button";
import { HeroMap } from "./HeroMap";

export function Hero() {
  return (
    <section className="relative flex min-h-[calc(100dvh-4rem)] flex-col items-center overflow-hidden px-4 pt-12 sm:px-6 sm:pt-16">
      <div
        className="uf-enter flex max-w-4xl flex-col items-center text-center"
        style={{ animationDelay: "40ms" }}
      >
        <h1 className="mt-7 max-w-4xl text-5xl font-semibold leading-[0.92] tracking-[-0.075em] text-balance sm:text-7xl lg:text-8xl">
          Draw a London block.
          <span className="block uf-accent-text ">Watch it replan itself.</span>
        </h1>

        <p className="mt-6 max-w-2xl text-base leading-7 text-muted-foreground text-pretty sm:text-lg">
          UrbanFlux turns a drawn boundary into a regeneration scenario: roads,
          buildings, green space, population context, and live impact estimates
          from real London data.
        </p>

        <div className="mt-8 flex flex-wrap items-center justify-center gap-3">
          <Button
            asChild
            size="lg"
            className="group h-11 rounded-none p-4 shadow-lg border-none"
          >
            <Link href="/app">
              Launch the tool
              <ArrowRightIcon
                data-icon="inline-end"
                className="transition-transform duration-200 ease-out motion-safe:group-hover:translate-x-1"
              />
            </Link>
          </Button>
          <Button
            asChild
            size="lg"
            variant="outline"
            className="group h-11 rounded-none p-4 bg-background/50 backdrop-blur"
          >
            <a href="https://github.com/chigwell/UrbanFlux">
              <StarIcon
                data-icon="inline-start"
                className="transition-colors duration-100 group-hover:fill-yellow-400 group-hover:text-yellow-400"
              />
              Star on GitHub
            </a>
          </Button>
        </div>
      </div>

      <div
        className="uf-enter relative mt-12 w-full max-w-6xl"
        style={{ animationDelay: "160ms" }}
      >
        <div className="pointer-events-none absolute -inset-x-8 -top-8 h-32 bg-[radial-gradient(60%_70%_at_50%_0%,color-mix(in_oklch,var(--uf-accent)_18%,transparent),transparent_72%)] blur-2xl" />
        <div className="relative overflow-hidden border-[0.5px]  bg-card shadow-2xl shadow-foreground/10 ring-1 ring-foreground/10">
          <div className="relative bg-background">
            <Image
              src="/urbanflux-demo.png"
              alt="UrbanFlux CityTwin demo with generated buildings, roads, and planning controls over London"
              width={3456}
              height={1940}
              className="block h-auto w-full"
              priority
              unoptimized
            />
            <HeroMap />
            <div className="pointer-events-none absolute inset-0 ring-1 ring-inset ring-white/10" />
          </div>
        </div>
        <div className="pointer-events-none absolute inset-x-0 bottom-0 h-20 bg-linear-to-t from-background to-transparent" />
      </div>
    </section>
  );
}
