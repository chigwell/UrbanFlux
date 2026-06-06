# Frontend (Next.js)

Single-page app that consumes the backend `GET /hello` endpoint and displays the response.

## Run locally

### 1) Install dependencies

```bash
cd frontend
npm install
```

### 2) Set the API URL (optional)

By default the app expects the API at `http://127.0.0.1:8000`.
You can override with:

```bash
export NEXT_PUBLIC_API_URL=http://127.0.0.1:8000
```

### 3) Start Next.js

```bash
npm run dev
```

Then open: `http://localhost:3000`

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
- Production frontend URL: `https://urbanflux.pages.dev/`
