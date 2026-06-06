"use client";

import maplibregl from "maplibre-gl";
import { useTheme } from "next-themes";
import { useEffect, useRef, useState } from "react";

const STYLES = {
  dark: "https://tiles.openfreemap.org/styles/dark",
  light: "https://tiles.openfreemap.org/styles/positron",
};
const LONDON: [number, number] = [-0.1276, 51.5072];

export function HeroMap() {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const { resolvedTheme } = useTheme();
  const [ready, setReady] = useState(false);

  useEffect(() => {
    if (!containerRef.current) return;
    const style = resolvedTheme === "dark" ? STYLES.dark : STYLES.light;

    const map = new maplibregl.Map({
      container: containerRef.current,
      style,
      center: LONDON,
      zoom: 12.6,
      pitch: 58,
      bearing: -22,
      interactive: false,
      attributionControl: false,
    });

    let frame = 0;
    const reduceMotion = window.matchMedia(
      "(prefers-reduced-motion: reduce)",
    ).matches;
    const rotate = () => {
      map.setBearing(map.getBearing() + 0.012);
      frame = requestAnimationFrame(rotate);
    };

    map.on("load", () => {
      setReady(true);
      if (!reduceMotion) {
        frame = requestAnimationFrame(rotate);
      }
    });

    return () => {
      cancelAnimationFrame(frame);
      map.remove();
    };
  }, [resolvedTheme]);

  return (
    <div className="absolute inset-0">
      <div ref={containerRef} className="size-full" />
      {!ready && (
        <div className="absolute inset-0 animate-pulse bg-linear-to-br from-muted to-background" />
      )}
      <div className="pointer-events-none absolute left-[18%] top-[30%] h-[32%] w-[52%] -rotate-6 rounded-[34%] border border-(--uf-accent)/70 bg-(--uf-accent)/10 shadow-[0_0_50px_color-mix(in_oklch,var(--uf-accent)_45%,transparent)]" />
      <div className="pointer-events-none absolute left-[20%] top-[44%] h-px w-[46%] rotate-[-18deg] bg-(--uf-accent)/60 shadow-[0_0_16px_color-mix(in_oklch,var(--uf-accent)_70%,transparent)]" />
      <div className="pointer-events-none absolute left-[37%] top-[35%] grid size-12 place-items-center rounded-full border border-(--uf-accent)/50 bg-background/20 backdrop-blur">
        <span className="size-1.5 rounded-full bg-(--uf-accent) shadow-[0_0_16px_var(--uf-accent)]" />
      </div>
      <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_48%_46%,transparent_36%,rgba(0,0,0,0.4)_100%)]" />
      <div className="pointer-events-none absolute inset-0 bg-linear-to-t from-background/90 via-background/5 to-transparent" />
    </div>
  );
}
