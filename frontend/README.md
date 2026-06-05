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
