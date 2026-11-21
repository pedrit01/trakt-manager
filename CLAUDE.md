# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Ground rules (always apply)

1. **Language:** always reply to the user in Spanish. OpenSpec artifacts, docs and user-facing text are also in Spanish.
2. **Commits:** never run `git commit` (nor push). At the end of every iteration, suggest a commit message in English (Conventional Commits style, e.g. `feat(sync): add idempotent list reconciliation`) for the user to commit themselves.
3. **Readable, documented code:** all code must be easy for a human to maintain:
   - Descriptive names (identifiers in English); small, single-purpose functions; no clever one-liners.
   - Every module, class and public function has a docstring in Spanish explaining what it does, its parameters, return value and errors raised.
   - Comments explain the *why* of non-obvious decisions (Trakt API quirks, retries, ordering), not what the code literally does.
   - Type hints on all function signatures.

## Project overview

Trakt manager creates and syncs Trakt (trakt.tv) lists from YAML/JSON definition files, via a web GUI, an HTTP API and a CLI, packaged in one Docker image (published to `ghcr.io/pedrit01/trakt-manager`). Behavior is specified in the OpenSpec changes under `openspec/changes/` (`dockerize-trakt-manager`, `add-web-gui`); the specs are the source of truth. `README.md` documents user-facing usage in Spanish.

The local Python is 3.9 but the project needs ≥3.11, so run everything in Docker.

## Commands

```bash
docker compose run --rm --build tests              # full test suite (pytest, Python 3.12)
docker compose run --rm tests tests/test_sync.py   # one file
docker compose run --rm tests -k shared_notes      # tests matching a name
docker compose up -d --build                       # GUI + API on :8000 (.env optional: without it, setup mode)
docker compose run --rm trakt-manager <command>    # any CLI command, e.g. sync lists/doomsday.yaml --dry-run
docker compose run --rm -p 8080:8080 --entrypoint python tests tests/demo_server.py   # GUI against the fake Trakt
```

There is no linter configured. Tests never call the real Trakt API: `tests/fake_trakt.py` is an in-memory fake (catalog, user lists, OAuth) plugged in through `httpx.MockTransport`. `tests/conftest.py` has `make_context` (an `AppContext` wired to it, injected into CLI tests via `CliRunner.invoke(..., obj=context)`) and `make_runtime` (an `AppRuntime`, passed to `create_app(runtime)`; values passed to it count as "from the environment"). The GUI JavaScript has no automated tests: check it in a real browser against `tests/demo_server.py`, and syntax-check it with `node --input-type=module --check`.

## Architecture

Layers in `src/trakt_manager/` (CLI and API are thin and share the same core and result models):

- `trakt_client.TraktClient`: the only HTTP layer. Handles Trakt headers, request pacing, 429 `Retry-After`, 5xx/network retries, and one token refresh on 401. `retry_rate_limits=False` exists because in the device flow a 429 means "poll slower".
- `auth`: `TokenStore` (`DATA_DIR/token.json`, mode 600), `TokenManager` (the `TokenSource` that refreshes tokens), `DeviceFlowAuthorizer` (CLI, foreground), and `BackgroundDeviceAuthorization` (API, background thread).
- `definitions`: pydantic models plus loading and validation. Errors are collected as `DefinitionIssue(entry_position, field, message)` with Spanish messages. Rules that span several fields raise `PydanticCustomError` with the field name in the error context.
- `resolver.EntryResolver`: turns entries into `DesiredItem`s (public endpoints only, so no session is needed). Explicit `ids` take priority over search. Search picks the exact year, then ±1, then the first result.
- `sync`: `plan_sync()` is a pure diff of desired items against the existing list, keyed by `(kind, trakt_id)` and never by note. `ListSynchronizer` resolves, plans, and applies the changes in this order: metadata, removals, additions, notes, then a final re-read and `reorder`. The list is matched by `trakt_list_id` or else by exact name. A dry run without a session plans as if the list were new.
- `trakt_lists.TraktListsAPI`: wraps the `/users/me/lists` endpoints.
- `app_context.AppContext`: lazily wires everything together for one configuration, so commands like `validate` work without `TRAKT_CLIENT_ID`. The client and the `TokenManager` are created together because each depends on the other.
- `settings_store`: `TRAKT_CLIENT_ID`, `TRAKT_CLIENT_SECRET` and `API_KEY` come from the environment (incl. `.env`), else from `DATA_DIR/settings.json` written by the GUI. `resolve_settings()` merges them and records each key's source (`env`/`stored`/`missing`). Environment always wins and cannot be edited from the GUI.
- `app_context.AppRuntime`: holds the *current* `AppContext` and rebuilds it on `reload()` when settings change (no restart). State that must survive reloads lives here: `SyncLocks`, the background device flow, and the `SetupGuard`. The API calls `runtime.current()` on every request; the CLI uses `AppRuntime(Settings()).current()` so it sees GUI-saved credentials too.
- `setup_guard.SetupGuard`: in setup mode (any of the three keys missing) the service still starts; a one-time code is logged at WARNING and `POST /setup` requires it (regenerated after 10 failures). This exists because Docker Desktop publishes ports on all interfaces.
- `definition_catalog.DefinitionCatalog`: merges `bundled` definitions (`LISTS_DIR`, read-only) with `saved` ones (`DATA_DIR/lists`, written by the GUI; saved wins on name clash). Names must match `^[a-z0-9][a-z0-9-]{0,63}$` (path-traversal guard; PUT/DELETE routes use `{name:path}` so bad names reach this check and get 422).
- `cli` (Typer) and `api` (FastAPI): `--json` output and API responses are the same pydantic models (`SyncResult`, `ValidationOutcome`). The API requires `X-API-Key` (compared against the current key on each request) except on `/health`, `/setup*` and the GUI; protected routes return 503 in setup mode. It runs as a single worker. Every response carries a strict CSP (`default-src 'self'`) except `/docs`, `/redoc` and `/openapi.json`, which load Swagger from a CDN.
- `web/`: the GUI, served by `StaticFiles` mounted at `/` *after* all API routes. Vanilla ES modules with no build step: `api.js` (fetch, X-API-Key from session/localStorage, Spanish error messages), `router.js` (`#/section/param`), `dom.js` (`h()` builds elements with `textContent`; never use `innerHTML` with data), `views/*.js` (one per section). The CSP forbids inline scripts and styles, so keep everything in files.

`create-tracklist.py` is the original standalone script. `lists/doomsday.yaml` and `tests/fixtures/original_roadmap.json` were migrated from it, and a test checks that the YAML still matches the original data. Per the migration plan, it is deleted only after a real end-to-end check against Trakt (task 9.2).

## OpenSpec workflow

This project uses OpenSpec (`openspec/config.yaml`, schema `spec-driven`). Changes live in `openspec/changes/<name>/`; main specs in `openspec/specs/` (empty until a change is archived). Use the `openspec-propose`, `openspec-apply-change`, and `openspec-archive-change` skills; validate with `openspec validate <change> --strict`.
