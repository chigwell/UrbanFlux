# Hero Live Animated Map — Design

**Date:** 2026-06-07
**Status:** Approved (design), pending implementation plan

## Goal

Make the marketing landing page (`/`) more impressive by replacing the static
hero screenshot (`/urbanflux-demo.png`) with a **live, self-driving MapLibre
instance** that flies over London, draws a block, generates a regeneration
layout, tunes it greener, and orbits the finished scenario — delivering on the
headline's promise: "Draw a London block. Watch it replan itself."

The static PNG is retained as the instant first paint (LCP) and as the fallback
whenever the live map is gated off or fails.

## Non-goals

- No changes to the geometry/generation engine (`lib/cityTwinMap.js`).
- No changes to the `/app` flow (`components/citytwin/*`).
- No new dependencies.
- The hero map is **not interactive** — it is a display, not a tool.
- No below-the-fold sections, video embed, or other hero variants (those were
  separate options not chosen for this work).

## Approach

**Self-contained `HeroMap` component with its own lightweight driver.**

A new `"use client"` component boots its own `initCityTwinMap` instance with
no-op output callbacks and runs a trimmed copy of the auto-improvement sequence
that `/app` already performs. This isolates all new logic, reuses the
battle-tested engine handle methods, and carries zero regression risk for the
working `/app` page.

Rejected alternatives:
- **Extract the auto-driver from `CityTwinApp` into a shared hook** — more DRY
  but touches the working `/app` flow (entangled with `controlsOpen`, the bottom
  sheet, animated settings). Regression risk not worth it for a marketing
  enhancement. Some orchestration duplication is acceptable; the hero version is
  strictly simpler.
- **Record a video and embed `<video>`** — cheaper, but the chosen direction is
  a genuinely live map.

## Components & files

### New: `components/home/HeroMap.tsx` (`"use client"`)

Owns:
- A container `div` (its own `ref`, **not** the `#map` id used by `/app`) that
  fills the hero frame (`absolute inset-0`), starts at `opacity-0`, and is
  `pointer-events-none`.
- Gating logic (see below) deciding whether to boot at all.
- The driver that runs the auto sequence and fades the layer in on first plan.
- Theme sync and cleanup.

### Changed: `components/home/Hero.tsx`

Keep the existing framed/shadowed container exactly. Inside it:
- The existing `<Image src="/urbanflux-demo.png" …>` **stays in normal flow** as
  the poster layer — it gives the frame its height and provides the instant LCP
  and the permanent fallback.
- `<HeroMap />` is layered `absolute inset-0` on top of the image, within the
  same frame.

No other Hero markup changes (headline, subhead, CTAs, glows untouched).

## Gating — decide whether to boot (checked on mount)

The live map boots **only** when all of these hold; otherwise the PNG stays and
no MapLibre instance is created:

1. `window.matchMedia("(prefers-reduced-motion: reduce)")` is **not** matched.
2. Viewport width `>= 768px` (phones keep the PNG).
3. Not data-saving / slow connection: if `navigator.connection` exists, skip
   when `saveData === true` or `effectiveType` is `"2g"` or `"slow-2g"`.
   (Absent API → treat as eligible.)
4. The frame is in view **and** the browser is idle: an `IntersectionObserver`
   on the frame, then `requestIdleCallback` (fallback `setTimeout`) before boot.

Boot happens at most once per page load. If gating fails, we never attempt
again for that load (no resize re-evaluation in v1 — YAGNI).

## Driver sequence (when booted)

Mirrors the `/app` auto-improvement flow, trimmed (no settings UI, no panels),
driven by an `AbortController` for cancellation:

1. `initCityTwinMap({ container, initialTheme, …no-op callbacks })`.
2. `await handle.flyToLondonOverview({ signal })`.
3. `await handle.pickAutoImprovementZone({ signal, reveal: true })`.
4. `await handle.waitForPlanRender({ signal, minGeneratedFeatures: 3,
   allowExisting: true, timeoutMs })`. If it returns `false`, retry
   `pickAutoImprovementZone` + `waitForPlanRender` **once** (same one-retry
   fallback `/app` uses for sparse map context).
5. A quick "greener" tune: nudge a small number of settings toward greener
   values via `handle.setSetting`, then `await handle.waitForPlanRender(...)`
   for the improved plan. (Lighter than `/app`'s fully animated parameter sweep.)
6. `handle.startAutoOrbit({ signal })`. **One pass, then orbit forever.**

On the first successful plan render, transition the map layer from `opacity-0`
to `opacity-100` (CSS transition) so it fades in over the poster PNG.

## Theme

- `initialTheme` derived from `next-themes` `resolvedTheme` at boot.
- A `useEffect` calls `handle.setTheme(theme)` when the resolved theme changes.

## Failure handling & cleanup

- **Driver throws / times out / aborts:** call `handle.destroy()` and leave the
  PNG showing (the map layer never fades in). `AbortError` is swallowed silently;
  other errors are `console.error`-logged. No user-facing toast on the marketing
  page. This is a graceful degradation to the existing static experience, not a
  silent swallow of an unexpected state — the page's contract is "show the hero
  visual," which the PNG still satisfies.
- **Unmount:** abort the controller, `handle.stopAutoOrbit()`, `handle.destroy()`.

## Data flow

```
mount
  -> gating checks (reduced-motion / width / connection)
       fail -> stay on PNG, done
       pass -> IntersectionObserver(in view) + requestIdleCallback
                  -> boot driver (AbortController)
                       overview -> pick zone -> waitForPlan (1 retry)
                         -> tune greener -> waitForPlan
                         -> startAutoOrbit (forever)
                       on first plan render -> fade map layer in over PNG
                       on error/timeout/abort -> destroy, PNG stays
unmount -> abort + stopAutoOrbit + destroy
```

## Engine reuse surface (already exists, from `lib/cityTwinMap.d.ts`)

`initCityTwinMap(options) -> handle` with: `flyToLondonOverview`,
`pickAutoImprovementZone`, `waitForPlanRender`, `setSetting`, `startAutoOrbit`,
`stopAutoOrbit`, `setTheme`, `destroy`. Container option accepts an
`HTMLElement`, so a `ref` element is passed directly (no DOM-id coupling).

The engine's population/impact network fetches still fire on selection; the
hero passes no-op `onPopulation`/`onImpact` callbacks and ignores the results.

## CSS notes

- The map layer is `absolute inset-0 pointer-events-none` with an
  `opacity`/`transition-opacity` for the fade-in. The CTAs and scrolling work
  normally over the non-interactive map.
- The engine still creates `.vertex-marker` / `.midpoint-marker` DOM nodes and
  MapLibre's own canvas; those rely on styles in `app/globals.css`, which stay
  as-is. The hero container does not reuse the `#map` id — it gets its size from
  filling the framed parent (which is sized by the poster image).

## Testing / verification

- `npx tsc --noEmit` and `npm run build` (static export) must pass — the gates
  per CLAUDE.md.
- Manual verification on `/`:
  - Desktop, motion allowed: PNG paints instantly, live map fades in within a
    few seconds, runs the sequence, ends orbiting; CTAs remain clickable.
  - `prefers-reduced-motion: reduce`: PNG only, no MapLibre instance.
  - Narrow viewport (`< 768px`): PNG only.
  - Forced driver failure (e.g. offline): PNG remains, no broken UI.
  - Theme toggle updates the live map.
- No automated test harness exists for the frontend map (engine is imperative
  MapLibre); verification is the typecheck/build gates plus manual checks.

## Out of scope / future

- Resize re-evaluation of gating after initial load.
- Cycling through multiple zones (chosen behaviour is one pass + orbit).
- Below-the-fold sections, stat counters, video — separate future work.
