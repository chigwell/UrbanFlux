# Frontend (Next.js CityTwin)

Static-export Next.js (App Router) app, written in TypeScript and styled with
Tailwind CSS v4 + shadcn/ui. It uses MapLibre GL, OpenFreeMap tiles and the
Overpass API to let users draw a London polygon, inspect nearby urban context
and generate an interactive regeneration scenario.

## Routes

- `/` — marketing landing page (shadcn, live MapLibre hero).
- `/app` — the interactive CityTwin tool.

## Run locally

### 1) Install dependencies

```bash
cd frontend
npm install
```

### 2) Start Next.js

```bash
npm run dev
```

Then open: `http://localhost:3000` (landing) and `/app` (tool).

## Architecture (tool)

The geometry/generation engine lives in `lib/cityTwinMap.js` (framework-agnostic
MapLibre + turf). It no longer touches the DOM by id: React mounts it once via
`initCityTwinMap(options)`, which returns a **handle** (`setSetting`, `setTheme`,
`setAllowWater`, `loadDemo`, `clearZone`, `undo`, `fit`, `destroy`) and emits
output through callbacks (`onStatus`, `onMetrics`, `onScenario`, `onReport`,
`onHint`, `onPills`, `onToast`). Types are in `lib/cityTwinMap.d.ts`. The shadcn
controls in `components/citytwin/*` read React state and write through the handle.

## Main functionality

- MapLibre-based London map
- Demo regeneration zone loaded by default
- Click-to-draw polygon editing
- Draggable vertices and midpoint handles
- Urban controls for density, green space, parking, roads, alignment and height
- Light/dark basemap toggle (synced with the site theme via `next-themes`)
- Water protection toggle
- Overpass context for roads, water, buildings and parks
- Generated roads, buildings, green space, parking and impact metrics

## GitHub Actions deploy (Cloudflare Pages)

Workflow file: `.github/workflows/deploy.yml`

### Required GitHub secrets

- `CLOUDFLARE_API_TOKEN`
- `CLOUDFLARE_ACCOUNT_ID`
- `CLOUDFLARE_PROJECT_NAME`

Push to `main` triggers build and deploy to Cloudflare Pages.

### Notes for Cloudflare Pages setup

- Add your Cloudflare Pages project name in `CLOUDFLARE_PROJECT_NAME`.
- This setup uses Next.js static export (`output: "export"`) and deploys directory `out`.
- Production frontend URL: `https://urbanflux.london/`
- Cloudflare Pages fallback URL: `https://urbanflux.pages.dev/`
