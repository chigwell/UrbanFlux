"use client";

import { useEffect, useRef, useState } from "react";
import { useTheme } from "next-themes";
import { initCityTwinMap } from "@/lib/cityTwinMap";
import type { CityTwinHandle, CityTwinTheme } from "@/lib/cityTwinMap";
import { sleep } from "@/lib/abortable";
import {
  AUTO_TIMING,
  DEFAULT_SETTINGS,
  buildRandomGreenerSettings,
} from "@/components/citytwin/settings";

/** Below this viewport width, phones keep the static poster (no live map). */
const MIN_LIVE_WIDTH = 768;

function prefersReducedMotion() {
  return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

function isSlowConnection() {
  const conn = (
    navigator as Navigator & {
      connection?: { saveData?: boolean; effectiveType?: string };
    }
  ).connection;
  if (!conn) return false;
  if (conn.saveData) return true;
  return conn.effectiveType === "2g" || conn.effectiveType === "slow-2g";
}

/** All gates must pass before we create any MapLibre instance. */
function canBootLiveMap() {
  if (typeof window === "undefined") return false;
  if (prefersReducedMotion()) return false;
  if (window.innerWidth < MIN_LIVE_WIDTH) return false;
  if (isSlowConnection()) return false;
  return true;
}

export function HeroMap() {
  const { resolvedTheme } = useTheme();
  const containerRef = useRef<HTMLDivElement | null>(null);
  const handleRef = useRef<CityTwinHandle | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const themeRef = useRef<CityTwinTheme>("light");
  const [revealed, setRevealed] = useState(false);

  // Keep latest theme in a ref (boot is deferred, so a captured value goes
  // stale) and push live theme changes into a running map instance.
  useEffect(() => {
    themeRef.current = resolvedTheme === "dark" ? "dark" : "light";
    handleRef.current?.setTheme(themeRef.current);
  }, [resolvedTheme]);

  useEffect(() => {
    const container = containerRef.current;
    if (!container || !canBootLiveMap()) return;

    let cancelled = false;
    let idleHandle: number | null = null;
    let observer: IntersectionObserver | null = null;

    const runDriver = async (handle: CityTwinHandle) => {
      const controller = new AbortController();
      abortRef.current = controller;
      const signal = controller.signal;

      try {
        await handle.flyToLondonOverview({ signal });
        await sleep(AUTO_TIMING.pauseAfterOverviewMs, signal);

        await handle.pickAutoImprovementZone({ signal, reveal: true });
        let rendered = await handle.waitForPlanRender({
          signal,
          timeoutMs: AUTO_TIMING.waitForInitialPlanTimeoutMs,
          minGeneratedFeatures: 3,
          allowExisting: true,
        });

        // Sparse map context (e.g. over a park/river): try one other zone.
        if (!rendered) {
          await handle.pickAutoImprovementZone({ signal, reveal: true });
          rendered = await handle.waitForPlanRender({
            signal,
            timeoutMs: AUTO_TIMING.waitForInitialPlanTimeoutMs,
            minGeneratedFeatures: 3,
            allowExisting: true,
          });
        }

        // First plan is up — fade the live map in over the poster image.
        if (!signal.aborted) setRevealed(true);

        // Quick "greener" tune, then wait for the improved plan.
        const target = buildRandomGreenerSettings(DEFAULT_SETTINGS);
        (Object.keys(target) as (keyof typeof target)[]).forEach((key) => {
          handle.setSetting(key, target[key]);
        });
        await handle.waitForPlanRender({
          signal,
          timeoutMs: AUTO_TIMING.waitForImprovedPlanTimeoutMs,
          minGeneratedFeatures: rendered ? 3 : 1,
        });

        handle.startAutoOrbit({ signal });
      } catch (error) {
        if (error instanceof DOMException && error.name === "AbortError") {
          return;
        }
        // Graceful degradation: tear the map down and leave the poster showing.
        console.error("Hero live map failed", error);
        handle.stopAutoOrbit();
        handle.destroy();
        if (handleRef.current === handle) handleRef.current = null;
        setRevealed(false);
      }
    };

    const boot = () => {
      if (cancelled || handleRef.current) return;
      const handle = initCityTwinMap({
        container,
        initialTheme: themeRef.current,
        initialAllowWater: false,
        initialSettings: DEFAULT_SETTINGS,
        // The hero ignores all engine output — it is a display, not a tool.
        onStatus: () => {},
        onMetrics: () => {},
        onScenario: () => {},
        onReport: () => {},
        onHint: () => {},
        onPills: () => {},
        onPopulation: () => {},
        onImpact: () => {},
        onToast: () => {},
        onAutoInterrupted: () => {},
      });
      handleRef.current = handle;
      void runDriver(handle);
    };

    const scheduleBoot = () => {
      if (cancelled) return;
      if (typeof window.requestIdleCallback === "function") {
        idleHandle = window.requestIdleCallback(() => boot(), { timeout: 2000 });
      } else {
        idleHandle = window.setTimeout(boot, 200);
      }
    };

    observer = new IntersectionObserver(
      (entries) => {
        if (entries.some((entry) => entry.isIntersecting)) {
          observer?.disconnect();
          observer = null;
          scheduleBoot();
        }
      },
      { threshold: 0.25 },
    );
    observer.observe(container);

    return () => {
      cancelled = true;
      observer?.disconnect();
      if (idleHandle !== null) {
        if (typeof window.cancelIdleCallback === "function") {
          window.cancelIdleCallback(idleHandle);
        } else {
          window.clearTimeout(idleHandle);
        }
      }
      abortRef.current?.abort();
      abortRef.current = null;
      const handle = handleRef.current;
      handleRef.current = null;
      if (handle) {
        handle.stopAutoOrbit();
        handle.destroy();
      }
    };
    // Boot logic runs once; theme is handled via themeRef + the effect above.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div
      ref={containerRef}
      aria-hidden
      className={`pointer-events-none absolute inset-0 transition-opacity duration-700 ease-out ${
        revealed ? "opacity-100" : "opacity-0"
      }`}
    />
  );
}
