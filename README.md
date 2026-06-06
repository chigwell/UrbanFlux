# UrbanFlux

UrbanFlux is a Next.js CityTwin map frontend with a FastAPI backend.

## Live URLs

- Frontend: https://urbanflux.london/
- API: https://api.urbanflux.london/
- Cloudflare Pages fallback: https://urbanflux.pages.dev/

## Structure

```text
frontend/   Next.js CityTwin map app
backend/    FastAPI API
.github/    GitHub Actions deployment
```

## Local development

Frontend:

```bash
cd frontend
npm install
npm run dev
```

Backend:

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

## Deployment

Pushes to `main` run `.github/workflows/deploy.yml`.

- Frontend deploys to Cloudflare Pages project `urbanflux`.
- Backend deploys to the VPS at `161.97.187.158:/opt/urbanflux/backend`.

Detailed notes:

- `frontend/README.md`
- `backend/README.md`
