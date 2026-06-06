import Link from "next/link";
import { ArrowRightIcon } from "lucide-react";
import { Button } from "@/components/ui/button";

export function CtaBand() {
  return (
    <section className="mx-auto w-full max-w-6xl px-6 py-16 lg:py-24">
      <div className="flex flex-col items-center gap-6 rounded-3xl border bg-card px-6 py-14 text-center shadow-sm">
        <h2 className="max-w-2xl text-3xl font-semibold tracking-tight text-balance sm:text-4xl">
          Reimagine a corner of London in the next sixty seconds
        </h2>
        <p className="max-w-xl text-lg text-muted-foreground text-pretty">
          No sign-up, no setup. Open the tool, draw a zone, and watch the
          regeneration plan build itself.
        </p>
        <Button asChild size="lg">
          <Link href="/app">
            Launch the tool
            <ArrowRightIcon data-icon="inline-end" />
          </Link>
        </Button>
      </div>
    </section>
  );
}
