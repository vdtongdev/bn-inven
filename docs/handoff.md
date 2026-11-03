# Remote development handoff

Snapshot date: 2026-11-03. Continue BN-Inven work from `main`.

## Start on another machine

Use Linux or WSL with Git, Python, `uv`, Node.js and npm installed:

```bash
git clone https://github.com/vdtongdev/bn-inven.git
cd bn-inven
bash ./start-dev.sh
```

The launcher syncs backend dependencies, installs frontend dependencies when
needed, explicitly applies Alembic migrations, and starts the API, worker and
frontend. Open <http://localhost:5173>; `/api` requests proxy to port 8001.
Press Ctrl+C to stop the services. The default AI provider is `mock` and requires
no paid API key. See [README](../README.md) and [deployment](deployment.md) for
configuration and Docker startup.

Create a fresh environment on the new machine. Do not copy a Windows or WSL
virtual environment or `node_modules` between operating systems. Local
`/mnt/c` permission issues are recorded in
[the historical ACL repair plan](plans/wsl-watchfiles-acl-repair.md); they are
machine-specific and do not authorize changes on another machine.

## Data and credentials

Git carries source, tests, migrations and plans. It excludes `.env`, local
databases, uploaded photos, dependency directories and logs. Recreate backend
secrets through environment variables or an ignored `.env`. A clone starts
without this machine's catalog or photos. To continue with existing catalog
data, transfer the SQLite database and uploads separately using the
[backup instructions](deployment.md); keep the database and images together.
Never commit credentials or runtime data to this public repository.

## Branches and local worktrees

At the start of this wrap-up, `main` was `72d8a7c` and already contained all
committed BN-Inven branch work. These branch names are retained on GitHub:

| Branch | Preserved work |
| --- | --- |
| `feat/ai-text-normalization` | Input-edit preservation base; normalization implementation is on `main` |
| `fix/input-reset` | Historical base; finished input-edit preservation is on `main` |
| `fix/upload-processing-status` | Upload processing and local API routing |
| `ui-catalog-review` | Catalog review UI |

Local `.worktrees/ai-text-normalization` and `.worktrees/input-reset` contain
uncommitted copies of source and tests that were compared with `main` and found
identical. Their unique plans, plus the upload-processing worktree's unique
plans, are preserved under `docs/plans/`. Local directories remain intact and
`.worktrees/` is ignored; they are not required to resume from a clone.

`.worktrees/foreman-codex-memory` belongs to a separate repository,
<https://github.com/vdtongdev/foreman>, on branch `codex-memory-store`. Its work
must be retrieved from that repository, not BN-Inven. The root
[Codex memory plan](plans/codex-memory-store.md) is a historical cross-project
record and does not describe BN-Inven application behavior.

## Validation boundary

This wrap-up changes documentation and Git bookkeeping only. Checks run in WSL
on 2026-11-03 produced these results:

- Backend `uv sync --extra dev && uv run pytest -q`: 64 passed, 6 warnings.
- Frontend `npm run build`: passed.
- Frontend `npm test`: 11 passed, 2 failed. `src/App.test.tsx` still expects
  the removed `Tạo lô` button. `src/live-dev-server.test.ts` could not connect
  to port 5173 because no development server was running.

These checks do not verify deployment or a fresh-machine startup. On a fresh
machine, run backend tests from `backend` with `uv run pytest`, and frontend
checks from `frontend` with `npm test` and `npm run build`. A successful workbook
download remains a GENERIC / DEMO export, not proof of MISA import compatibility.
