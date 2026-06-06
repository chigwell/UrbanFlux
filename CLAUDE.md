# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

UrbanFlux ("CityTwin") is a browser-side urban-regeneration map demo: the user draws a polygon over London, the app pulls live map context (roads, water, buildings, parks) and procedurally generates a road/building/green-space layout with impact metrics. It is two independent apps:

- `frontend/` — Next.js static-export app (the real product), TypeScript + Tailwind v4 + shadcn/ui. Two routes: `/` is the marketing landing, `/app` is the interactive CityTwin tool.
- `backend/` — FastAPI API for status checks, selected-area population, replanning impact metrics, and mapped London borough data. The frontend calls `/population` and `/impact`; the backend is deployed separately.

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

Backend tests live in `backend/tests` and CI runs `pytest tests` from the `backend/` directory on Python 3.12. Frontend typechecking/build gates remain `npx tsc --noEmit` and `npm run build`.

## Architecture

### Frontend: React + a bridged imperative engine

The geometry/generation engine still lives in `frontend/lib/cityTwinMap.js` (~2900 lines of framework-agnostic JS: MapLibre + turf). The heavy logic (context fetching, generation, MapLibre sources) is unchanged, **but the UI is no longer coupled by DOM `id`s** — it goes through a bridge:

- `initCityTwinMap(options)` is called once from `components/citytwin/CityTwinApp.tsx` in a `useEffect`. It returns a **handle** — `setSetting`, `setTheme`, `setAllowWater`, `loadDemo`, `clearZone`, `undo`, `fit`, `destroy` — and pushes all output through **callbacks** in `options`: `onStatus`, `onMetrics`, `onScenario`, `onReport`, `onHint`, `onPills`, `onToast`. Types live in `lib/cityTwinMap.d.ts`.
- `CityTwinApp.tsx` owns React state, renders the `#map` container + shadcn overlay cards (`ControlsCard`, `StatusCard`, `DashboardCard`, `LegendCard` in `components/citytwin/`), and wires controls: a shadcn `Slider`/`Switch`/`Button` change calls a handle method; an engine callback updates React state. Theme is synced with `next-themes` and `handle.setTheme`.
- The marketing landing (`/`) is plain shadcn in `components/marketing/*`; its `HeroMap.tsx` is a separate read-only MapLibre instance.

**Consequence:** there is no `getElementById` coupling anymore. shadcn `Slider`/`Switch` are *controlled* components — they must read React state and write through the handle (that's the whole reason for the bridge). Do **not** reintroduce DOM-id wiring. One CSS coupling remains: the engine creates plain `.vertex-marker` / `.midpoint-marker` DOM nodes and a `#map` container, styled in `app/globals.css` (outside shadcn) — keep those styles when editing CSS.

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

- `backend/main.py`: FastAPI route layer and public import surface. Implementation is split across `schemas.py`, `population.py`, `impact.py`, `borough_context.py`, and `nemotron_adapter.py`.
- Public backend routes: `GET /`, `GET /hello`, `POST /population`, `POST /impact`, and `GET /borough-data-test`.
- `/impact` computes deterministic London-data-first metrics first. Nemotron refinement is optional and falls back when `FAL_KEY` or `fal_client` is absent, the call times out, or the model returns invalid metric JSON.
- `backend/nemotron.py` is a standalone recommendation script; it is not imported by the FastAPI server.
- `.github/workflows/deploy.yml` runs on push to `main`:
  - Frontend → builds and deploys `frontend/out` to **Cloudflare Pages** (needs `CLOUDFLARE_API_TOKEN`, `CLOUDFLARE_ACCOUNT_ID`, `CLOUDFLARE_PROJECT_NAME`).
  - Backend → rsyncs `backend/` to a VPS at `/opt/urbanflux/backend`, reinstalls deps, restarts the `urbanflux-backend` systemd service (needs `VPS_*` secrets; see `backend/README.md` for the exact systemd command and secret values).
- Static export (`output: "export"` in `next.config.mjs`) means **no Next.js server features** — no API routes, no server components doing runtime data fetching, no `next/image` loader. Both `/` and `/app` prerender to static HTML and hydrate; anything touching `window`/MapLibre must be in a `"use client"` component and mounted in an effect. All dynamic behavior is client-side fetches to Overpass/tile servers.

Live: frontend `https://urbanflux.london/`, API `https://api.urbanflux.london/`.
