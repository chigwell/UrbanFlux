# UrbanFlux

UrbanFlux has a Next.js frontend and a FastAPI backend.

## Live URLs

- Frontend: https://urbanflux.pages.dev/
- Backend: http://161.97.187.158/

## Project structure

```text
backend/    FastAPI app
frontend/   Next.js app
.github/    GitHub Actions deploy workflow
```

## Local development

Run the backend:

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

Run the frontend:

```bash
cd frontend
npm install
npm run dev
```

The frontend expects the API at `http://127.0.0.1:8000` by default. Override it with:

```bash
export NEXT_PUBLIC_API_URL=http://127.0.0.1:8000
```

## Deployment

Deployment is handled by GitHub Actions on every push to `main`.

Workflow:

```text
.github/workflows/deploy.yml
```

The workflow deploys:

- `frontend/` to Cloudflare Pages project `urbanflux`
- `backend/` to the VPS at `161.97.187.158:/opt/urbanflux/backend`

## GitHub Secrets

Required Cloudflare secrets:

- `CLOUDFLARE_API_TOKEN`
- `CLOUDFLARE_ACCOUNT_ID`
- `CLOUDFLARE_PROJECT_NAME=urbanflux`

Required VPS secrets:

- `VPS_HOST=161.97.187.158`
- `VPS_USER=deploy`
- `VPS_SSH_PRIVATE_KEY`
- `VPS_SSH_PORT=22`
- `VPS_SERVICE_NAME=urbanflux-backend`

`VPS_SSH_PRIVATE_KEY` must be a private SSH key without a passphrase. Its public key must be present in:

```text
/home/deploy/.ssh/authorized_keys
```

## VPS setup

The backend runs as a `systemd` service behind Nginx.

Systemd unit:

```text
/etc/systemd/system/urbanflux-backend.service
```

Expected service command:

```bash
/opt/urbanflux/backend/.venv/bin/uvicorn main:app --host 127.0.0.1 --port 8000
```

Nginx should proxy public HTTP traffic to FastAPI:

```nginx
server {
    listen 80;
    server_name 161.97.187.158;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

The `deploy` user needs passwordless sudo for the deploy workflow:

```text
deploy ALL=(root) NOPASSWD: /usr/bin/apt-get, /usr/bin/systemctl, /bin/systemctl
```

## Useful checks

On the VPS:

```bash
curl -i http://127.0.0.1:8000/
curl -i http://127.0.0.1:8000/hello
systemctl status urbanflux-backend --no-pager
```

From outside:

```bash
curl -i http://161.97.187.158/
curl -i http://161.97.187.158/hello
```
