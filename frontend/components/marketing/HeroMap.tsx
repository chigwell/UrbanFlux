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
    const rotate = () => {
      map.setBearing(map.getBearing() + 0.012);
      frame = requestAnimationFrame(rotate);
    };

    map.on("load", () => {
      setReady(true);
      frame = requestAnimationFrame(rotate);
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
        <div className="absolute inset-0 animate-pulse bg-gradient-to-br from-muted to-background" />
      )}
      {/* readability scrim + edge fade */}
      <div className="pointer-events-none absolute inset-0 bg-gradient-to-t from-background via-background/10 to-transparent" />
    </div>
  );
}
