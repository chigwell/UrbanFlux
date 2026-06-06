# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

UrbanFlux ("CityTwin") is a browser-side urban-regeneration map demo: the user draws a polygon over London, the app pulls live map context (roads, water, buildings, parks) and procedurally generates a road/building/green-space layout with impact metrics. It is two independent apps:

- `frontend/` — Next.js static-export single-page app (the real product).
- `backend/` — FastAPI Hello-World API. **Not consumed by the frontend** today; deployed separately. The repo-root `main.py` is empty.

## Commands

Frontend (`cd frontend`):
```bash
npm install
npm run dev        # dev server at http://localhost:3000
npm run build      # static export to frontend/out/ (what Cloudflare Pages deploys)
npm run start      # serve a production build
```

Backend (`cd backend`):
```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

There is **no test suite, linter, or formatter configured** in either app. "Build passes" = `npm run build` (frontend) and the server importing cleanly (backend). Don't claim tests pass — there are none to run.

## Architecture

### Frontend: React shell + one imperative engine

The single most important thing to understand: **almost all logic lives in `frontend/lib/cityTwinMap.js` (~2900 lines of vanilla JS), not in the React components.**

- `app/page.js` → `components/CityTwinApp.js` ("use client") renders **static markup with specific DOM `id`s** and calls `initCityTwinMap()` once in `useEffect`.
- `cityTwinMap.js` is framework-agnostic. On init it grabs those elements via `document.getElementById(...)` (see the `dom` object at the top) and wires all event listeners, MapLibre map setup, fetching, generation, and rendering itself.
- The panel components (`ControlsPanel`, `DashboardPanel`, `LegendPanel`, `StatusPanel`, `IntroPanel`) are **dumb markup only** — no handlers, no state. They exist to declare the DOM `id`s the engine reaches for.

**Consequence:** the React components and the engine are coupled by string `id`s, not props. If you rename/remove an `id` in a component (e.g. a slider `id` in `ControlsPanel.js`, or `#demoButton`, `#allowWaterToggle`, `#statusText`), you must update the matching `getElementById`/`addEventListener` in `cityTwinMap.js`, and vice versa. There is no compile-time check linking them. The slider ids `density/green/parking/street/alignment/height` map directly to `state.settings` keys.

### The generation pipeline (inside cityTwinMap.js)

User edits polygon → debounced handlers → render. Two parallel debounced paths:

1. `scheduleContextFetch()` (~520ms) → `fetchContextForCurrentPolygon()`: fetches surrounding map features into `state.contextFeatures`, from two sources merged:
   - **Vector basemap** already loaded in MapLibre, via `queryRenderedFeatures` + `querySourceFeatures` (layer/source-layer names are discovered dynamically to tolerate different OpenFreeMap/OpenMapTiles/Protomaps schemas).
   - **Raw OSM** via Overpass API (`OVERPASS_ENDPOINTS` are tried in rotation on failure). `buildOverpassQuery` defines what's pulled.
   - Sets `state.contextStatus` (`vector`/`osm`/`partial`/`failed`) which gates generation.
2. `scheduleGeneration()` (~40ms) → `generateScenario()`: builds `state.latestStats` (road anchors, water obstacles, building-size estimates) then calls `generateUrbanLayout(...)` to produce the GeoJSON that is pushed into the three MapLibre sources.

**Three MapLibre GeoJSON sources** drive everything (set up in `initialiseMapLayers`): `selection` (the drawn polygon), `context` (fetched surroundings), `generated` (procedural output). Layers filter on a feature `properties.kind` / `roadClass` discriminator. Theme switching re-adds all layers on `style.load`.

**Coordinate math:** generation converts lng/lat into a local meter-based planar frame (`createLocalFrame`/`lngLatToLocal`) so geometry/turf operations work in meters, then converts back. `@turf/turf` is used heavily for buffering, intersection, point-in-polygon.

**Determinism:** `generateScenario` seeds a PRNG (`seededRandom(hashString(...))`) from the vertices + settings + water flag, so the same inputs always yield the same layout.

**Water protection:** when the "water override" toggle is off, generation **refuses to run** until real water masks are available (`waterContextReady()`), rather than guessing across rivers. This is intentional — don't "fix" it by drawing a fallback over water.

### Backend & deployment

- `backend/main.py`: FastAPI app, CORS open to `*`, routes `/` and `/hello`. That's the whole API.
- `.github/workflows/deploy.yml` runs on push to `main`:
  - Frontend → builds and deploys `frontend/out` to **Cloudflare Pages** (needs `CLOUDFLARE_API_TOKEN`, `CLOUDFLARE_ACCOUNT_ID`, `CLOUDFLARE_PROJECT_NAME`).
  - Backend → rsyncs `backend/` to a VPS at `/opt/urbanflux/backend`, reinstalls deps, restarts the `urbanflux-backend` systemd service (needs `VPS_*` secrets; see `backend/README.md` for the exact systemd command and secret values).
- Static export (`output: "export"` in `next.config.mjs`) means **no Next.js server features** — no API routes, no server components doing runtime data fetching, no `next/image` loader. All dynamic behavior is client-side fetches to Overpass/tile servers.

Live: frontend `https://urbanflux.london/`, API `https://api.urbanflux.london/`.
