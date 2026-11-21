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

Trakt manager creates and syncs Trakt (trakt.tv) lists from YAML/JSON definition files (`lists/`), via a CLI and an HTTP API, packaged in Docker. Behavior is specified in the OpenSpec change `openspec/changes/dockerize-trakt-manager/` (specs are the source of truth). `README.md` documents user-facing usage in Spanish.

The local Python is 3.9 but the project needs ≥3.11, so run everything in Docker.

## Commands

```bash
docker compose run --rm --build tests              # full test suite (pytest, Python 3.12)
docker compose run --rm tests tests/test_sync.py   # one file
docker compose run --rm tests -k shared_notes      # tests matching a name
docker compose up -d --build                       # API service (needs .env with API_KEY)
docker compose run --rm trakt-manager <command>    # any CLI command, e.g. sync lists/doomsday.yaml --dry-run
```

There is no linter configured. Tests never call the real Trakt API: `tests/fake_trakt.py` is an in-memory fake (catalog, user lists, OAuth) plugged in through `httpx.MockTransport`. `tests/conftest.py::make_context` builds an `AppContext` wired to it, and CLI/API tests inject it (`CliRunner.invoke(..., obj=context)`, `create_app(context)`).

## Architecture

Layers in `src/trakt_manager/` (CLI and API are thin and share the same core and result models):

- `trakt_client.TraktClient`: the only HTTP layer. Handles Trakt headers, request pacing, 429 `Retry-After`, 5xx/network retries, and one token refresh on 401. `retry_rate_limits=False` exists because in the device flow a 429 means "poll slower".
- `auth`: `TokenStore` (`DATA_DIR/token.json`, mode 600), `TokenManager` (the `TokenSource` that refreshes tokens), `DeviceFlowAuthorizer` (CLI, foreground), and `BackgroundDeviceAuthorization` (API, background thread).
- `definitions`: pydantic models plus loading and validation. Errors are collected as `DefinitionIssue(entry_position, field, message)` with Spanish messages. Rules that span several fields raise `PydanticCustomError` with the field name in the error context.
- `resolver.EntryResolver`: turns entries into `DesiredItem`s (public endpoints only, so no session is needed). Explicit `ids` take priority over search. Search picks the exact year, then ±1, then the first result.
- `sync`: `plan_sync()` is a pure diff of desired items against the existing list, keyed by `(kind, trakt_id)` and never by note. `ListSynchronizer` resolves, plans, and applies the changes in this order: metadata, removals, additions, notes, then a final re-read and `reorder`. The list is matched by `trakt_list_id` or else by exact name. A dry run without a session plans as if the list were new.
- `trakt_lists.TraktListsAPI`: wraps the `/users/me/lists` endpoints.
- `app_context.AppContext`: lazily wires everything together, so commands like `validate` work without `TRAKT_CLIENT_ID`. The client and the `TokenManager` are created together because each depends on the other.
- `cli` (Typer) and `api` (FastAPI): `--json` output and API responses are the same pydantic models (`SyncResult`, `ValidationOutcome`). The API requires `X-API-Key` on every route except `/health`, refuses to start without `API_KEY`, runs as a single worker, and uses an in-memory per-list lock for real syncs (409 when the lock is busy).

`create-tracklist.py` is the original standalone script. `lists/doomsday.yaml` and `tests/fixtures/original_roadmap.json` were migrated from it, and a test checks that the YAML still matches the original data. Per the migration plan, it is deleted only after a real end-to-end check against Trakt (task 9.2).

## OpenSpec workflow

This project uses OpenSpec (`openspec/config.yaml`, schema `spec-driven`). Changes live in `openspec/changes/<name>/`; main specs in `openspec/specs/` (empty until a change is archived). Use the `openspec-propose`, `openspec-apply-change`, and `openspec-archive-change` skills; validate with `openspec validate <change> --strict`.
