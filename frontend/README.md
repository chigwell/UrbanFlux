# Frontend (Next.js CityTwin Map)

Static single-page CityTwin map app. It uses MapLibre GL, OpenFreeMap tiles and Overpass API to let users draw a London polygon, inspect nearby urban context and generate an interactive regeneration scenario.

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

Then open: `http://localhost:3000`

## Main functionality

- MapLibre-based London map
- Demo regeneration zone loaded by default
- Click-to-draw polygon editing
- Draggable vertices and midpoint handles
- Urban controls for density, green space, parking, roads, alignment and height
- Light/dark basemap toggle
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
