# Local API port collision fix

## Objective

Keep the browser on BN-Inven's Vite origin at port 5173 and route API calls through the same origin with relative `/api` URLs. Vite proxies `/api` to the local BN-Inven backend on port 8001. Port 8000 remains available to the other app. Do not expose the backend port to frontend browser code or change Docker's internal ports.

## Diagnosis

`frontend/src/api.ts` currently defaults to `http://localhost:8000`, which targets the other app. `start-dev.sh` starts Uvicorn on its default port 8000. WSL inspection found 8001 free. Backend CORS already allows the UI origin `http://localhost:5173`; keep the existing CORS configuration unchanged. With the Vite proxy, browser requests stay same-origin and do not need to address port 8001 directly.

## Implementation sequence

1. Add focused regression coverage that checks the frontend API base uses relative `/api` and that Vite proxies `/api` to the backend on 8001.
2. Configure Vite's `/api` proxy to target `http://127.0.0.1:8001`, preserving the `/api` path.
3. Change the frontend API base fallback to `/api` so browser requests remain on port 5173.
4. Start Uvicorn explicitly on port 8001 in `start-dev.sh`; update the launcher's API/docs status text and README local API instructions. Keep the backend bound to its local development interface and leave Docker internal port mappings unchanged.
5. Verify the focused frontend/proxy checks and run `bash ./start-dev.sh`; confirm the browser-facing API requests use relative `/api` paths, Vite forwards them to backend port 8001, and both services reach ready state.

## Acceptance

- Browser uses only the Vite origin on port 5173 for UI and API requests.
- Frontend API base is relative `/api`; no browser bundle default points to port 8001 or 8000.
- Vite forwards `/api` requests to the BN-Inven backend on port 8001.
- The other app on port 8000 remains untouched.
- Existing backend CORS settings and Docker internal service ports remain unchanged.
- Focused proxy/API-base regression checks pass and the launcher starts API on 8001 and Vite on 5173.

## Startup constraint

The main-checkout BN-Inven frontend currently occupies port 5173. The user must stop that existing instance before the worktree app can claim 5173. Do not terminate it as part of this change without the user's approval.
