# Knowledge Engine — RevRag AI

**Owner:** Sneha (Member 3)
**Branch:** `member3/knowledge-engine`

The Knowledge Engine receives observations from the Android controller (Pallavi)
and actions from the exploration agent (Deekshitha), decides screen identity,
builds the app map and journeys, analyses screenshots, and exports a
**Knowledge Pack** for the dashboard / rebuild layer (Suma).

It never touches the emulator. It is a pure HTTP + SQLite service.

---

## Quick start

```bash
# from the repository root
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-knowledge.txt      # or merge into requirements.txt
cp .env.example .env

uvicorn knowledge.api:app --reload --port 8100
```

Interactive API docs: <http://localhost:8100/docs>

Run the tests:

```bash
pytest tests -q
```

Tests use a temporary SQLite file per test via the `temp_db` fixture, so the
real database at `KNOWLEDGE_DB_PATH` is never touched.

---

## Architecture

```
POST /observations ──► ScreenManager ──► fingerprint ──► SQLite (dedup)
POST /actions      ──► actions table
POST /transitions  ──► transitions table
                            │
                            ▼
                     graph_builder (NetworkX)
                            │
                ┌───────────┴────────────┐
                ▼                        ▼
         journey_builder          design_analyzer (OpenCV)
                └───────────┬────────────┘
                            ▼
                     knowledge_pack
                            │
      GET /knowledge-pack/latest ──► Suma / dashboard / rebuild
```

| Module | Responsibility |
| --- | --- |
| `schemas.py` | Pydantic v2 request/response models |
| `models.py` | SQLite DDL + row dataclasses |
| `database.py` | Connections, `init_db`, transactions |
| `repositories.py` | Every SQL statement |
| `fingerprint.py` | Deterministic screen hashing |
| `screen_manager.py` | Dedup + stable screen ids |
| `graph_builder.py` | NetworkX app map |
| `journey_builder.py` | Path discovery |
| `design_analyzer.py` | Screenshot colour/layout evidence |
| `knowledge_pack.py` | Pack assembly, validation, export |
| `stability_checker.py` | Repeat-scan comparison |
| `api.py` | FastAPI wiring only |

Layers are separate on purpose: business logic modules do not import FastAPI,
and `fingerprint`, `graph_builder`, `journey_builder`, `design_analyzer` and
`stability_checker` do not import Pydantic either. They work on plain dicts,
which is what makes them straightforward to unit test.

---

## API

Every endpoint is scoped by `scan_id`, which defaults to `scan_000001`. Send a
different `scan_id` to explore the same app again without mixing the results.

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/health` | Liveness |
| POST | `/observations` | Ingest an observation |
| POST | `/actions` | Ingest an action |
| POST | `/transitions` | Create an edge between two known screens |
| GET | `/screens` | List deduplicated screens |
| GET | `/screens/{screen_id}` | One screen with elements |
| GET | `/app-map` | Nodes + edges + graph statistics |
| GET | `/journeys` | Discovered paths |
| POST | `/knowledge-pack/generate` | Build and store a pack |
| GET | `/knowledge-pack/latest` | Newest pack |
| POST | `/stability/compare` | Compare two scans |
| GET | `/scans` | List known scans |

### Examples

```bash
# health
curl -s localhost:8100/health

# Pallavi: send an observation
curl -s -X POST localhost:8100/observations \
  -H 'Content-Type: application/json' \
  -d @data/sample/observation.json

curl -s -X POST localhost:8100/observations \
  -H 'Content-Type: application/json' \
  -d @data/sample/second_observation.json

# Deekshitha: send an action
curl -s -X POST localhost:8100/actions \
  -H 'Content-Type: application/json' \
  -d @data/sample/action.json

# link the two screens
curl -s -X POST localhost:8100/transitions \
  -H 'Content-Type: application/json' \
  -d @data/sample/transition.json

# reads
curl -s "localhost:8100/screens?scan_id=scan_000001"
curl -s localhost:8100/app-map
curl -s localhost:8100/journeys

# Suma: generate and fetch the pack
curl -s -X POST localhost:8100/knowledge-pack/generate \
  -H 'Content-Type: application/json' -d '{"package_name":"com.example.app"}'
curl -s localhost:8100/knowledge-pack/latest

# repeat-scan stability
curl -s -X POST localhost:8100/stability/compare \
  -H 'Content-Type: application/json' \
  -d '{"previous_scan_id":"scan_000001","current_scan_id":"scan_000002"}'
```

### Status codes

| Code | Meaning |
| --- | --- |
| 200 | Success |
| 404 | Unknown screen / no pack generated yet |
| 409 | `observation_id` already ingested in this scan |
| 422 | Validation failure (bad bounds, missing field, bad `screen_id` pattern) |
| 500 | Storage failure |

---

## How each teammate integrates

**Pallavi (controller) →** `POST /observations` with the exact JSON from the
shared observation contract (`elements`, `screenshot_path`, `ui_tree_path`).
Nothing else is required. `screen_id` may be included but is treated as
advisory (see below). Optionally add `"scan_id"` to separate runs.

**Deekshitha (explorer) →** `POST /actions`. Only `action_id` and `action_type`
are required today. When she can supply `source_screen_id` **and**
`target_screen_id`, a transition is created automatically; otherwise the action
is stored and she (or the controller) can call `POST /transitions` once both
screens are known. `timestamp`, `result`, `success` and `metadata` are already
accepted, so adding them later needs no API change.

**Suma (dashboard / rebuild) →** `GET /knowledge-pack/latest` for everything in
one document, or `GET /app-map` and `GET /journeys` for live views. Packs are
also written to `KNOWLEDGE_PACK_OUTPUT_DIR` as `pack_000001.json`.

---

## Screen identity

A fingerprint is `SHA-256` of a canonical JSON document containing:
package name, activity, and for every element its type, normalized text,
normalized content description, resource id, `clickable`/`enabled`/`scrollable`,
and bounds. Text is lowercased, trimmed, and internal whitespace collapsed.
Elements are sorted before hashing so UI-tree ordering does not matter.

Deliberately **excluded**: `observation_id`, `screen_id`, `element_id`,
timestamps and file paths. Two scans of the same UI must hash identically.

A second, text-insensitive **structural** fingerprint is stored alongside
(bounds bucketed to 16px). It is not used for deduplication; it powers the
similarity score and the "changed screen" category in stability reports.

### Deduplication

1. Fingerprint the observation.
2. Look for that fingerprint within the scan (unique index).
3. Hit → reuse the screen id, `observation_count += 1`, merge any new elements.
4. Miss → allocate the next id and insert the screen.

The controller's `screen_id` is **never** used to merge screens. It is stored on
the observation row as `reported_screen_id`, and a warning is returned when it
disagrees with the engine's decision.

Ids are allocated from a `screen_counter` column inside the same
`BEGIN IMMEDIATE` transaction as the insert, so concurrent requests cannot
produce duplicate ids. There is no in-memory counter.

---

## Graph and journeys

`MultiDiGraph`: nodes are screens, edges are transitions. Two different actions
between the same pair of screens stay two edges. **An edge whose source or
target screen is unknown is skipped and reported as a warning** — no node is
ever invented to satisfy an edge.

Journeys are shortest paths from each component's entry screen (in-degree 0, or
the lowest screen id when a component is fully cyclic) to every reachable
screen, bounded by `KNOWLEDGE_MAX_JOURNEY_LENGTH` and capped at
`KNOWLEDGE_MAX_JOURNEYS`. Because only shortest paths are used, a cycle can
never be traversed twice.

Names come from element text when a recognisable keyword is present
(`Login Journey`), otherwise from activity labels, otherwise
`Screen 1 to Screen 4`. Every journey carries `metadata.user_confirmed = false`:
these are explorer-observed paths, not validated user flows.

---

## Design analysis — what it can and cannot do

Measured reasonably well: dominant colours (k-means with a fixed seed, so output
is deterministic), background colour, image dimensions, mean brightness.

Approximated, and labelled as such: button and text colours are sampled from the
UI tree's element bounds, not from shape detection; spacing is the pixel gap
between stacked element bounds.

**Not attempted:** font family, font size in sp, corner radius. A screenshot
cannot support those claims, so `font_sizes` and `corner_radius_estimates` stay
empty rather than being guessed.

A missing or corrupt screenshot never raises. It produces a warning and lowers
`confidence`, which is simply `analyzed_count / screenshot_count`.

---

## Knowledge Pack

`pack_id` and `source_observation_ids` match the approved shared schema exactly.
Every other field is a **provisional** Member 3 extension documented in
`schemas/knowledge_pack.v0_2.schema.json`. The shared
`schemas/knowledge_pack.schema.json` has not been modified.

Output is deterministic: all collections are sorted by stable keys, so two runs
over identical data differ only in `generated_at`.

---

## Stability comparison

Matching runs in three passes — exact fingerprint (matched), structural
fingerprint (changed: text differs), then best Jaccard similarity ≥ 0.6
(changed: layout drifted). Leftovers are added/removed.

```
stability_score = (matched + 0.5 × changed) / max(previous_count, current_count)
```

This is an **engineering metric for explorer repeatability**, not a scientific
guarantee about the app. Every report repeats that caveat in `warnings`.

---

## Environment variables

| Variable | Default | Purpose |
| --- | --- | --- |
| `KNOWLEDGE_DB_PATH` | `data/knowledge.db` | SQLite file |
| `KNOWLEDGE_PACK_OUTPUT_DIR` | `data/output` | Pack JSON output |
| `KNOWLEDGE_LOG_LEVEL` | `INFO` | Log level |
| `KNOWLEDGE_MEDIA_ROOT` | `.` | Base dir for relative screenshot paths |
| `KNOWLEDGE_MAX_JOURNEY_LENGTH` | `8` | Max edges per journey |
| `KNOWLEDGE_MAX_JOURNEYS` | `200` | Max journeys materialised |

---

## Known limitations

- Deduplication is exact-fingerprint only. A screen whose text changes on every
  visit (a clock, a live feed) becomes a new screen each time. The structural
  fingerprint is stored and ready if the team decides to switch.
- Transitions are only created when both screens are already known.
- Journeys are shortest paths, so alternative routes to the same screen are not
  all enumerated.
- Design analysis needs the screenshot files to be reachable from this service's
  filesystem (`KNOWLEDGE_MEDIA_ROOT`).
- `ui_tree_path` is stored but not parsed; the `elements` array is the contract.
- SQLite with WAL handles the expected single-explorer load. It is not intended
  for many concurrent writers.

## Future improvements

Similarity-based merging behind a flag, XML UI-tree parsing as a fallback when
`elements` is absent, per-screen design records, weighted/ranked journeys, and
Alembic migrations if the team adopts them.
