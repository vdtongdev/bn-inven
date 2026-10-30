# Plan: Frontend dependency vulnerability remediation

## Goal

Reconcile the frontend dependency tree with current advisories, apply only verified compatible fixes, preserve the PWA/build workflow, and document any transitive risk that cannot yet be removed safely.

## Current evidence

- `frontend/package.json` and `frontend/package-lock.json` are consistent after the implementation update. Current pinned versions are Vite `6.4.5`, PostCSS `8.5.32`, Vitest `4.1.12`, and `vite-plugin-pwa` `0.21.1`; all frontend packages are now in `devDependencies` because they are build/test inputs for a static site.
- The dependency tree still contains `vite-plugin-pwa@0.21.1 -> workbox-build -> @rollup/plugin-node-resolve -> deepmerge@4.3.1`. `npm ls --all` exited 0 after the update.
- The latest full npm audit reported **4 low findings**; `npm audit --omit=dev` reported **0 findings**. The remaining low advisory GHSA-gcqx-w48m-w2h4 is from `deepmerge@4.3.1` in the PWA/Workbox build chain. No safe fix was identified; a breaking downgrade to `vite-plugin-pwa@0.2.1` was declined.
- `frontend/Dockerfile` runs `npm ci` in the Node build stage and copies only `/web/dist` into the final `caddy:2-alpine` image. The standard production build succeeded as `bn-inven-frontend-check:latest` (`sha256:29e106d651ac0cb2d6cc368a9f74937833a246b344638ee157bc14957cda09f9`). Inspection verified `/srv/index.html`, `/srv/manifest.webmanifest`, and `/srv/sw.js`, with no `node` executable or `/web/node_modules`. Earlier TLS failures remain historical; their cause is unknown. WSL mirrored networking was not tested. `docs/deployment.md` records the same verification.
- Earlier attempts had an npm `10.9.4` Arborist `edgesOut` error and npm `11` registry/TLS failures. The implementation run completed `npm ci --cache ./.npm-cache` using the in-repository cache; package manifests and lockfile were updated in that implementation pass. No TLS verification was disabled and no global npm runtime was installed.
- Candidate-version review remains traceable: Vite `6.4.5` ([release](https://github.com/vitejs/vite/releases/tag/v6.4.5)), PostCSS `8.5.32` ([release](https://github.com/postcss/postcss/releases/tag/8.5.32)), and Vitest `4.1.12` ([release](https://github.com/vitest-dev/vitest/releases/tag/v4.1.12)). Vitest `3.2.7` is not sufficient for the current `@vitest/mocker` advisory findings; the maintainer advisory records `4.1.12` as patched ([GHSA-qxg6-89mg-rqv8](https://github.com/vitest-dev/vitest/security/advisories/GHSA-qxg6-89mg-rqv8)).

## Dependency-update error diagnosis

- A dry-run update of Vitest `4.1.12` alone with Node `22.22.1` / npm `10.9.4` reproducibly crashes in Arborist `#loadPeerSet` with `Cannot read properties of null (reading 'edgesOut')`. Vite/PostCSS-only and Vitest `3.2.7` control updates succeed, but `3.2.7` is not a security fix for the current mocker advisories.
- The resolver traversed Vitest optional peer packages and `@vitejs/devtools`; this matches the failure pattern in [npm/cli issue #9787](https://github.com/npm/cli/issues/9787), but the match is not proof of a project dependency defect. At the time of reproduction, there was no project `.npmrc` and dependency metadata was unchanged.
- The later Windows Node `24.22.0` / npm `11.19.1` retry first encountered `EACCES` fetching `vitest` and could not reach the audit endpoint. A subsequent implementation run succeeded with `npm ci --cache ./.npm-cache`; this records the successful run without claiming the earlier registry failure's general cause is fixed.
- Earlier npm `11` CLI download attempts failed TLS/OpenSSL during response-body transfer over HTTP/2 and HTTP/1.1 despite successful headers. Strict TLS remains enabled; no TLS or project `.npmrc` setting was changed.

## Implementation outcome

- `npm ci --cache ./.npm-cache` passed.
- `npm test` passed (**1/1**); `npm run build` passed and emitted `manifest.webmanifest`, `sw.js`, and Workbox output.
- `npm ls --all` exited 0. The latest audits report 4 low findings for the full tree and 0 with `--omit=dev`.
- Docker retry evidence (2026-10-29): normal `docker build -t bn-inven-frontend-check .` and `docker build --network=host -t bn-inven-frontend-check .` from `frontend/` both reached `RUN npm ci` and failed with `ERR_SSL_CIPHER_OPERATION_FAILED`; build context was `173.7MB`. Read-only diagnosis reproduced response-body corruption in WSL and a Node container: `36,183`-byte metadata and a `635,617`-byte Vite tarball downloaded, while larger metadata failed after about `1,883,475` bytes with `decryption failed or bad record mac`; a Node fetch container stopped near `1,324,604` bytes. The exact failing concurrent npm tarball request and transport component are unknown. WSL Docker access works; the Windows Docker CLI remains unavailable. No source, TLS, proxy, or daemon configuration was changed.
- Bounded retry/context result (2026-10-29): `frontend/.dockerignore` is now present and the Dockerfile uses bounded npm fetch retries with TLS validation enabled. An ordinary `docker build -t bn-inven-frontend-check .` reported context `329.2kB` (down from `173.7MB`) but still failed at `RUN npm ci` with `ERR_SSL_CIPHER_OPERATION_FAILED` and exit code 1. No final image was created; its Caddy filesystem and static assets remain uninspected.
- Offline-cache image diagnostic (2026-10-29): Windows `npm ci --cache ./.npm-cache` populated 500 packages. `npm pack @rollup/rollup-linux-x64-musl@4.66.0 --cache ./.npm-cache --pack-destination ./.rollup-pack-check --json` cached the locked Linux-musl optional package; the generated tarball was 960,957 bytes and `npm cache ls` showed its registry URL. In a separate temporary context excluding `node_modules`, Docker reported `36.44MB`; offline `npm ci` succeeded with 498 packages and the Vite/PWA build passed, generating `manifest.webmanifest`, `sw.js`, and Workbox output. The Caddy final stage built successfully as image `bn-inven-frontend-offline-check:latest` (`29e106d651ac`). A disposable inspection verified `/srv/index.html`, `/srv/manifest.webmanifest`, and `/srv/sw.js`; it reported `NODE_ABSENT`, `NODE_MODULES_ABSENT`, and `STATIC_PWA_FILES_OK`. The cache, pack destination, and temporary context were removed after verification; the image is retained. This validated offline packaging; the standard online production build was separately verified afterward.
- Docker reliability follow-up (2026-10-29): added `frontend/.dockerignore` for `node_modules/`, `dist/`, `coverage/`, `.npm-cache/`, TypeScript build info, local environment files, and logs. Added bounded `npm ci --fetch-retries=5 --fetch-retry-factor=2 --fetch-retry-maxtimeout=120000` in the Node builder, retaining strict TLS. The ordinary build context fell from `173.7MB` to `329.2kB`. The build still failed at `RUN npm ci` with `ERR_SSL_CIPHER_OPERATION_FAILED` and exit code 1. The retry flags did not recover this run; final image build and inspection remain unverified. The ignore file remains because its context reduction is confirmed; the bounded retry options are harmless and retained.
- Standard production Docker verification (2026-10-29): after the user ran `wsl --update` and confirmed WSL/Docker registry response tests passed, `docker build -t bn-inven-frontend-check .` from `frontend/` completed with exit 0 and created the image. A direct container inspection confirmed `/srv/index.html`, `/srv/manifest.webmanifest`, and `/srv/sw.js` exist, while `node` and `/web/node_modules` are absent (`STATIC_PWA_FILES_OK`). Earlier TLS failures remain historical; the exact cause of improved network behavior is unknown. Mirrored networking and WSL shutdown/restart were not tested, and no `.wslconfig` or project source setting was changed.
- Dependency remediation is **partial, not complete**: GHSA-gcqx-w48m-w2h4 remains through `deepmerge@4.3.1` in the PWA/Workbox build dependency chain. No safe fix has been identified; the breaking `vite-plugin-pwa@0.2.1` downgrade was declined. The audit finding alone does not establish exploitability in the static Caddy image.

## Tasks

1. **Refresh and record the advisory baseline.** Status: complete.
   - Agent: implementer
   - The implementation re-ran `npm audit --json`, `npm audit --omit=dev --json`, and `npm ls --all` from `frontend/`. Reported result: 4 low full-tree findings, 0 omit-dev findings, and `npm ls --all` exit 0.
   - Record advisory IDs, severity, affected ranges, fixed versions, dependency paths, and whether the path is build-only or present in the shipped image. Check each advisory against its primary maintainer or GitHub Advisory Database entry before selecting versions.

2. **Patch direct dependencies with the smallest compatible updates.** Status: complete.
   - Agent: implementer
   - The implementation updated Vite to `6.4.5`, PostCSS to `8.5.32`, and Vitest to `4.1.12`, compatible with the current React/Vite/PWA build and confirmed by install, test, build, and audit runs. Vitest `3.2.7` was not used as a fix for the current mocker advisories.
   - The package lock was regenerated through the npm workflow; no lock metadata was hand-edited and `npm audit fix --force` was not used.

3. **Resolve or explicitly bound the deepmerge transitive finding.** Status: unresolved with documented limitation.
   - Agent: implementer
   - Recheck the `vite-plugin-pwa -> workbox-build -> @rollup/plugin-node-resolve -> deepmerge` path and whether a supported upstream release removes or patches it.
   - Current status: GHSA-gcqx-w48m-w2h4 remains via `deepmerge@4.3.1` in the PWA/Workbox build chain, with no patched version identified. Do not use a `deepmerge@4.1.1` override: the locked `@rollup/plugin-node-resolve@16.0.3` declares `deepmerge` as `^4.2.2`, so `4.1.1` is outside its supported range; its implementation also copies keys with `destination[key] = ...`, resembling the prototype-pollution concern recorded in [deepmerge issue #158](https://github.com/TehShrike/deepmerge/issues/158). The advisory covers `4.2.0-4.3.1` with no patched release ([GHSA-gcqx-w48m-w2h4](https://github.com/advisories/GHSA-gcqx-w48m-w2h4)). Version `4.1.1` is therefore not established as a safe compatible fix. API shape alone is insufficient because 4.2.x included behavior changes; see the [node-resolve package range](https://github.com/rollup/plugins/blob/master/packages/node-resolve/package.json), [4.1.1 source](https://raw.githubusercontent.com/TehShrike/deepmerge/v4.1.1/index.js), and [deepmerge changelog](https://github.com/TehShrike/deepmerge/blob/master/changelog.md). Keep the low build-time finding documented and unresolved; do not force-downgrade `vite-plugin-pwa` to `0.2.1` or claim all vulnerabilities are cleared. Recheck for a supported PWA/Workbox update that removes the vulnerable node.

4. **Align dependency placement and the static deployment build.** Status: complete; standard production image build and final image inspection verified.
   - Agent: implementer
   - Classify root packages based on actual use. Since the final Docker image serves static `/web/dist` through Caddy, React/runtime UI packages are bundled at build time; Vite, TypeScript, PWA, CSS, and test packages are build/test tools. Place packages in `dependencies` only if a Node runtime actually needs them after build; otherwise use `devDependencies`.
   - The Docker builder now uses `npm ci` and installs `devDependencies` so Vite, PWA service-worker generation, CSS processing, and tests remain available. Cloudflare Pages builds must also include `devDependencies`. The final Caddy image copies only `dist`; the standard production build and final image inspection are now verified (see current evidence above).

5. **Verify behavior and re-audit.** Status: partial; standard production Docker build and final-image inspection verified, dependency advisory remains unresolved.
   - Agent: implementer
   - The clean install, frontend test, frontend build, dependency-tree check, and both audits have been run. The standard online build from the production Dockerfile now succeeds, and inspection confirms static PWA assets with no Node runtime/dependencies in the Caddy image. Earlier TLS failures are retained as history; do not claim their exact underlying cause is fixed.
   - Report GHSA-gcqx-w48m-w2h4 as unresolved within the four low full-tree audit findings; the omit-dev audit reports zero findings.

6. **Reduce Docker context and retry bounded registry failures.** Status: context reduction and standard production build verified; earlier TLS failure remains historical with unknown cause.
   - Agent: implementer
   - Reproduced npm TLS body failures from Docker and WSL without disabling TLS. The transport layer responsible remains unknown.
   - Added focused `frontend/.dockerignore` entries and verified the build context decreased from `173.7MB` to `329.2kB`.
   - Added bounded fetch retry flags to `npm ci`; a subsequent standard production build completed successfully after WSL/Docker registry response tests passed. Dependency versions and TLS settings were preserved; no proxy/network/daemon settings were changed.
   - The standard online production build and final-image inspection passed after WSL/Docker registry response tests succeeded. The offline-cache image verification is secondary corroboration (task 7); neither result identifies the cause of the earlier TLS failures or verifies mirrored networking.

7. **Try offline-cache image verification in an isolated temporary build context.** Status: offline image build and inspection passed with the missing Linux-musl package seeded into cache.
   - Agent: implementer
   - Confirmed `.npm-cache`, `.offline-build-context`, and `.rollup-pack-check` were absent and resolved within the repository. Windows `npm ci --cache ./.npm-cache` succeeded and added 500 packages. Packed `@rollup/rollup-linux-x64-musl@4.66.0` to the task-local destination (960,957 bytes) and verified its cache entry with `npm cache ls`.
   - Built from a distinct temporary context containing only the manifests, required sources/configuration, Caddyfile, and cache. Context size was `36.44MB`. Offline `npm ci` added 498 packages; `npm run build` passed and generated the PWA manifest, service worker, and Workbox file.
   - The Caddy final stage built successfully as `bn-inven-frontend-offline-check:latest`. `docker run --rm --entrypoint sh ...` verified `/srv/index.html`, `/srv/manifest.webmanifest`, `/srv/sw.js`, no `node` executable, and no `/web/node_modules`.
   - Cleaned only the newly generated `.npm-cache`, `.offline-build-context`, and `.rollup-pack-check` after resolving them beneath the repository. The verification image is retained. Production Docker/package files, TLS settings, and Docker/network configuration were unchanged. This offline check does not resolve or verify the production online registry path.

## Acceptance checks

- `cd frontend; npm ci --cache ./.npm-cache` passed.
- `cd frontend; npm test` passed 1/1; `npm run build` passed and emitted the PWA manifest and service worker.
- Fresh audits report 4 low full-tree findings and 0 with `--omit=dev`; the remaining deepmerge advisory is documented and unresolved.
- `cd frontend; npm ls --all` exited 0 and reported the updated dependency graph.
- The standard production `docker build -t bn-inven-frontend-check .` from `frontend/` passed with exit 0. Inspection verified `/srv/index.html`, `/srv/manifest.webmanifest`, `/srv/sw.js`, and absence of `node` and `/web/node_modules`. Earlier `ERR_SSL_CIPHER_OPERATION_FAILED` build failures remain historical; their exact cause is unknown. WSL mirrored networking was not tested, and TLS remained enabled.
- The separate-context offline check succeeded after seeding the locked `@rollup/rollup-linux-x64-musl@4.66.0` tarball into the cache. Offline install/build passed and the retained Caddy image was inspected: static PWA files are present, Node and `/web/node_modules` are absent. This validates cached offline packaging only; it is secondary to the now-verified standard online production build.
- No forced downgrade or unverified override is used to silence npm audit.

## Files in scope

- `frontend/package.json`
- `frontend/package-lock.json`
- `frontend/Dockerfile`
- `frontend/.dockerignore` (new)
- Temporary isolated context under `frontend/` only for the diagnostic in task 7; remove only newly created context/cache after resolved-path checks.
- `docs/deployment.md` only if build or residual-risk guidance changes

## Constraints

- Keep Vite, TypeScript, React, Tailwind, `vite-plugin-pwa`, and Vitest-based checks working.
- Audit output flags known vulnerable ranges; it does not by itself prove an exploit path in the final static Caddy image.
- Do not modify application behavior or expand into backend dependency remediation.
- Do not claim complete vulnerability remediation while the deepmerge advisory remains; do not claim Docker image validation until a successful build and inspection are recorded.
