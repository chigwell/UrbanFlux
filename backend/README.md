# Backend (FastAPI)

Simple FastAPI backend with CORS enabled and a single Hello World endpoint.

## Run locally

### 1) Install dependencies

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2) Start the API

```bash
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

### 3) Check endpoints

- `GET /` -> `{"message": "UrbanFlux backend is running"}`
- `GET /hello` -> `{"message": "Hello World"}`

## GitHub Actions deploy (VPS)

Workflow file: `.github/workflows/deploy.yml`

Push to `main` uploads `backend/` to:

```text
/opt/urbanflux/backend
```

The workflow installs Python dependencies on the VPS and restarts the `systemd` service.

### Required GitHub secrets

- `VPS_HOST`
- `VPS_USER`
- `VPS_SSH_PRIVATE_KEY`
- `VPS_SSH_PORT`
- `VPS_SERVICE_NAME`

Current expected values:

- `VPS_HOST=161.97.187.158`
- `VPS_USER=deploy`
- `VPS_SSH_PORT=22`
- `VPS_SERVICE_NAME=urbanflux-backend`

### VPS service

Expected `systemd` service file:

```text
/etc/systemd/system/urbanflux-backend.service
```

Expected service command:

```bash
/opt/urbanflux/backend/.venv/bin/uvicorn main:app --host 127.0.0.1 --port 8000
```

Check status:

```bash
sudo systemctl status urbanflux-backend --no-pager
```

Check local VPS endpoint:

```bash
curl -i http://127.0.0.1:8000/
curl -i http://127.0.0.1:8000/hello
```
