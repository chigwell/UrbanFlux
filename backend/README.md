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
