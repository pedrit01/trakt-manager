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

## Project status

Trakt manager: a tool to create and manage Trakt (trakt.tv) lists remotely. The repo is at a very early stage — the only code is `create-tracklist.py`, a standalone script. The planned architecture (Python package with shared core, Typer CLI, FastAPI service, Docker image, YAML/JSON list definitions) is specified but **not yet implemented** in the OpenSpec change `openspec/changes/dockerize-trakt-manager/` (`proposal.md`, `design.md`, `specs/`, `tasks.md`). Read it before building anything; it is the source of truth for intended behavior. Once that change is applied, update this file with the real commands.

## Running the current script

Standard library only, Python 3.8+. Needs a Trakt OAuth app (redirect URI `urn:ietf:wg:oauth:2.0:oob`).

```bash
export TRAKT_CLIENT_ID=... TRAKT_CLIENT_SECRET=...
python3 create-tracklist.py --dry-run          # resolve items only, no account changes (needs only CLIENT_ID)
python3 create-tracklist.py                    # create the list
python3 create-tracklist.py --include-extras   # also add entries with is_extra=true
```

There are no tests, linter or build yet.

## How `create-tracklist.py` works

- `ROADMAP` (embedded JSON) is the ordered list of entries: `kind` is `movie` or `episode_list` (show `query` + `season` + `episodes`), with `block`, `note`, `is_extra`.
- Resolution: `/search/{movie|show}` preferring exact year, then ±1 year, then first result; episodes via `/shows/{slug}/seasons/{s}/episodes/{e}`.
- Auth: OAuth device flow; token cached in `./.trakt_token.json` (relative to CWD, never refreshed).
- List creation: `POST /users/me/lists` with `sort_by: rank`, then items are inserted one entry at a time to preserve the interleaved movie/episode order.
- Known bug (fix planned in the OpenSpec change): movies are indexed by `notes` in `movie_map`, but several movies share the same note, so duplicates get added and others are lost. Items must be keyed by Trakt id instead. Re-running also creates a second list.

## OpenSpec workflow

This project uses OpenSpec (`openspec/config.yaml`, schema `spec-driven`). Changes live in `openspec/changes/<name>/`; main specs in `openspec/specs/` (empty until a change is archived). Use the `openspec-propose`, `openspec-apply-change`, and `openspec-archive-change` skills; validate with `openspec validate <change> --strict`.
