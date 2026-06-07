# Hero Live Animated Map Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the static hero screenshot on the `/` landing page with a live, self-driving MapLibre instance that flies over London, generates a regeneration layout, tunes it greener, and orbits — falling back to the existing PNG when gated off or on failure.

**Architecture:** A new self-contained `"use client"` component (`HeroMap`) boots its own `initCityTwinMap` instance with no-op callbacks and runs a trimmed copy of the auto-improvement sequence the `/app` page already performs. It overlays the existing poster `<Image>` inside the same framed container and fades in once the first plan renders. No engine or `/app` changes; no new dependencies.

**Tech Stack:** Next.js (static export) + React + TypeScript, MapLibre via the existing `lib/cityTwinMap.js` engine and its typed bridge `lib/cityTwinMap.d.ts`, `next-themes`, Tailwind v4.

**Testing note:** The frontend map is imperative MapLibre with no unit-test harness (per spec + CLAUDE.md). The verification gates are `npx tsc --noEmit`, `npm run build` (static export), and the manual observations specified in each task. Tasks therefore use typecheck/build + manual checks in place of automated tests — this is the project's real verification contract, not a substitute for missing tests.

**Working directory:** All paths are relative to `frontend/`. Run all `npx`/`npm` commands from `frontend/`. The active git branch is `feat/hero-live-map`.

---

## File Structure

- **Create:** `frontend/components/home/HeroMap.tsx` — the entire live-map feature: gating, lazy boot, the auto-sequence driver, theme sync, cleanup, and the overlay container element. One responsibility: drive and render the hero's live map.
- **Modify:** `frontend/components/home/Hero.tsx` — layer `<HeroMap />` over the existing poster `<Image>` inside the current framed container. Markup-only change; stays a server component.

Reused without modification:
- `frontend/lib/cityTwinMap.js` / `.d.ts` — `initCityTwinMap` and the handle methods.
- `frontend/lib/abortable.ts` — `sleep`.
- `frontend/components/citytwin/settings.ts` — `AUTO_TIMING`, `DEFAULT_SETTINGS`, `buildRandomGreenerSettings`.

---

## Task 1: Create the `HeroMap` component

**Files:**
- Create: `frontend/components/home/HeroMap.tsx`

- [ ] **Step 1: Write the component**

Create `frontend/components/home/HeroMap.tsx` with exactly this content:

```tsx
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
```

- [ ] **Step 2: Typecheck the new file**

Run (from `frontend/`): `npx tsc --noEmit`
Expected: PASS (exit 0), no errors. In particular no errors about `requestIdleCallback`, `connection`, or the `initCityTwinMap` option/handle shapes. If `requestIdleCallback`/`cancelIdleCallback` are reported as missing on `window`, that indicates the TS `lib` is older than expected — stop and report rather than widening types.

- [ ] **Step 3: Commit**

```bash
git add frontend/components/home/HeroMap.tsx
git commit -m "feat: add self-driving HeroMap component for landing hero"
```

---

## Task 2: Layer `HeroMap` over the poster in `Hero.tsx`

**Files:**
- Modify: `frontend/components/home/Hero.tsx`

The current framed container (around lines 60-72) is:

```tsx
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
            <div className="pointer-events-none absolute inset-0 ring-1 ring-inset ring-white/10" />
          </div>
        </div>
```

- [ ] **Step 1: Add the `HeroMap` import**

At the top of `frontend/components/home/Hero.tsx`, add this import after the existing `Button` import (line 4):

```tsx
import { HeroMap } from "./HeroMap";
```

- [ ] **Step 2: Insert `<HeroMap />` between the `<Image>` and the inset-ring div**

Replace this exact block:

```tsx
            <div className="pointer-events-none absolute inset-0 ring-1 ring-inset ring-white/10" />
```

with:

```tsx
            <HeroMap />
            <div className="pointer-events-none absolute inset-0 ring-1 ring-inset ring-white/10" />
```

The `<Image>` stays in normal flow (it sizes the frame and is the instant LCP + permanent fallback). `<HeroMap />` is `absolute inset-0` and overlays it; the inset-ring div stays last so the ring renders above the live map.

- [ ] **Step 3: Typecheck**

Run (from `frontend/`): `npx tsc --noEmit`
Expected: PASS (exit 0).

- [ ] **Step 4: Production build (static export gate)**

Run (from `frontend/`): `npm run build`
Expected: PASS — static export to `frontend/out/` completes with no errors. Confirms the client component and engine import behave under static export.

- [ ] **Step 5: Commit**

```bash
git add frontend/components/home/Hero.tsx
git commit -m "feat: overlay live HeroMap on the landing hero poster"
```

---

## Task 3: Manual verification

No automated harness covers the live map; verify behaviour by hand against the spec's acceptance criteria.

**Files:** none (verification only).

- [ ] **Step 1: Start the dev server**

Run (from `frontend/`): `npm run dev`
Open `http://localhost:3000/`.

- [ ] **Step 2: Desktop, motion allowed (happy path)**

In a desktop-width window with normal motion settings:
- Expected: the poster paints immediately. Within a few seconds the live map fades in over it, flies to a London overview, selects a block, generates roads/buildings/green space, nudges greener, then settles into a slow continuous orbit.
- Expected: the "Launch the tool" / "Star on GitHub" buttons remain fully clickable, and the page scrolls normally over the map (the layer is `pointer-events-none`).

- [ ] **Step 3: Reduced motion**

Enable "Reduce motion" at the OS level (macOS: System Settings → Accessibility → Display → Reduce motion), reload `/`.
- Expected: only the static poster shows; no map canvas appears. Confirm in DevTools that no `maplibregl` canvas is added inside the frame.

- [ ] **Step 4: Narrow viewport**

Resize the window below 768px (or use DevTools device toolbar), reload `/`.
- Expected: poster only, no live map.

- [ ] **Step 5: Failure fallback**

With a desktop window, open DevTools → Network → set to "Offline", then reload `/`.
- Expected: the poster remains visible and the layout is intact (the map never fades in, no error UI). A single `console.error("Hero live map failed", …)` is acceptable; there should be no unhandled promise rejection and no thrown error breaking the page. Set Network back to "Online" afterwards.

- [ ] **Step 6: Theme toggle**

Back online with the live map running, click the theme toggle in the header.
- Expected: the live map restyles to match light/dark along with the rest of the page.

- [ ] **Step 7: Record results**

If every check passes, the feature is complete — there is nothing to commit (verification only). If any check fails, capture the exact symptom and console output and stop for diagnosis (use the systematic-debugging skill) rather than patching blindly.

---

## Self-Review

**Spec coverage:**
- Replace screenshot in-place, PNG as poster/fallback → Task 2 (overlay; `<Image>` retained).
- New `HeroMap.tsx` `"use client"`, own instance, no-op callbacks → Task 1.
- Gating (reduced-motion / `<768px` / slow connection / in-view + idle) → Task 1 `canBootLiveMap` + IntersectionObserver + `requestIdleCallback`; verified in Task 3 steps 2-4.
- Driver sequence (overview → pick zone → waitForPlan with one retry → greener tune → orbit forever) → Task 1 `runDriver`.
- Fade-in on first plan render → `setRevealed(true)` + opacity transition (Task 1).
- Non-interactive → `pointer-events-none` on the container (Task 1).
- Theme initial + live sync → `themeRef` + theme effect (Task 1).
- Failure → destroy + keep poster; unmount → abort + stopAutoOrbit + destroy → Task 1 catch + cleanup; verified Task 3 step 5.
- No engine/`/app` changes, no new deps → only two files touched.
- Verification gates `tsc --noEmit` + `npm run build` + manual → Tasks 1-3.

**Placeholder scan:** No TBD/TODO; all code is complete and copy-paste ready; no "handle errors" hand-waving (the catch block is shown in full).

**Type/name consistency:** `handleRef`, `abortRef`, `themeRef`, `setRevealed`, `runDriver`, `boot`, `scheduleBoot`, `canBootLiveMap` are used consistently across Task 1. Handle methods (`flyToLondonOverview`, `pickAutoImprovementZone`, `waitForPlanRender`, `setSetting`, `startAutoOrbit`, `stopAutoOrbit`, `setTheme`, `destroy`) and option fields all match `lib/cityTwinMap.d.ts`. Reused helpers (`sleep`, `AUTO_TIMING`, `DEFAULT_SETTINGS`, `buildRandomGreenerSettings`) match their source modules. `<HeroMap />` import path in Task 2 matches the file created in Task 1.
