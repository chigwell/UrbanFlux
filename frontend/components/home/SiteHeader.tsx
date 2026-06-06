import Link from "next/link";
import { ArrowRightIcon } from "lucide-react";
import { Button } from "@/components/ui/button";
import { ThemeToggle } from "@/components/theme-toggle";

export function SiteHeader() {
  return (
    <header className="sticky top-0 z-50">
      <div className="mx-auto flex h-16 w-full max-w-6xl items-center justify-between gap-4 px-6">
        <Link
          href="/"
          className="group flex items-center gap-2 text-xl font-semibold tracking-tight"
        >
          UrbanFlux
        </Link>
        <div className="flex items-center gap-1.5">
          <ThemeToggle />
          <Button asChild size="lg" className="rounded-none p-4">
            <Link href="/app">
              Open app
              <ArrowRightIcon data-icon="inline-end" />
            </Link>
          </Button>
        </div>
      </div>
    </header>
  );
}
