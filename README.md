# BN-Inven

BN-Inven helps staff digitize a small business product catalog from phone photos: capture product labels, review AI extraction suggestions, approve catalog details, and export a workbook. It does not track stock quantities or warehouse transactions.

The repository contains a React/Vite installable PWA and a FastAPI modular monolith. A database-backed worker uses the mock vision provider by default, so local development requires no paid API key. The initial workbook is explicitly **GENERIC / DEMO** and is not an official MISA template.

An optional OpenRouter vision adapter can be enabled on the backend with `AI_PROVIDER=openrouter`, `AI_API_KEY`, and `AI_MODEL` in the ignored root `.env`. Mock remains the default; implementation checks never call the paid API. See [deployment](docs/deployment.md) for secret handling and provider limits.

## Run locally in WSL

From the repository root in WSL, run:

```bash
bash ./start-dev.sh
```

The script checks for `uv`, Node.js, and npm; syncs backend dependencies; installs frontend dependencies if needed; applies Alembic migrations; then starts the API, durable worker, and PWA together. Logs stay in the terminal. Press **Ctrl+C** to stop all three services.

Open <http://localhost:5173>. The API defaults to <http://localhost:8000>; interactive API docs are at <http://localhost:8000/docs>. Vite's `VITE_API_BASE_URL` can point to another API origin.

## Checks

```powershell
cd backend; uv run pytest
cd frontend; npm test; npm run build
```

## Docker

Copy `.env.example` to `.env`, set the real `DOMAIN`, `BASIC_AUTH_USER`, and `BASIC_AUTH_HASH`. Build the images, run the migration explicitly, then start the stack:

```sh
docker compose build
docker compose run --rm api alembic upgrade head
docker compose up -d
```

Only Caddy publishes host ports 80/443. It requires HTTP Basic Authentication and terminates HTTPS. API and frontend containers have no direct public port. For Cloudflare Pages, follow the separate access boundary in [deployment.md](docs/deployment.md).

See [architecture](docs/architecture.md), [domain model](docs/domain-model.md), [deployment and backup](docs/deployment.md), and [roadmap](docs/roadmap.md).
