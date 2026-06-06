import { SiteHeader } from "@/components/home/SiteHeader";
import { Hero } from "@/components/home/Hero";

export default function HomePage() {
  return (
    <div className="uf-page-bg relative flex min-h-dvh flex-col overflow-hidden">
      <div className="uf-grid-bg pointer-events-none absolute inset-x-0 top-0 h-168 opacity-60" />
      <div className="uf-noise pointer-events-none absolute inset-0 opacity-[0.025] mix-blend-overlay" />
      <SiteHeader />
      <main className="relative flex-1">
        <Hero />
      </main>
    </div>
  );
}
