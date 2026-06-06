import Link from "next/link";

export function SiteFooter() {
  return (
    <footer className="border-t">
      <div className="mx-auto flex w-full max-w-6xl flex-col gap-6 px-6 py-10 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center gap-2 font-semibold">
          <span className="grid size-7 place-items-center rounded-lg bg-primary text-xs text-primary-foreground">
            UF
          </span>
          UrbanFlux
        </div>
        <nav className="flex flex-wrap gap-x-6 gap-y-2 text-sm text-muted-foreground">
          <Link href="/app" className="transition-colors hover:text-foreground">
            Launch app
          </Link>
          <a
            href="https://urbanflux.london/"
            className="transition-colors hover:text-foreground"
          >
            urbanflux.london
          </a>
          <a
            href="https://github.com/chigwell/UrbanFlux"
            className="transition-colors hover:text-foreground"
          >
            GitHub
          </a>
        </nav>
        <p className="text-sm text-muted-foreground">
          Built with MapLibre, OpenFreeMap &amp; OpenStreetMap.
        </p>
      </div>
    </footer>
  );
}
