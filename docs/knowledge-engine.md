# Knowledge Engine — design decisions, assumptions, open questions

**Owner:** Sneha (Member 3) · **Branch:** `member3/knowledge-engine`

`knowledge/README.md` is the usage guide. This document records *why* things
are the way they are, every assumption that was made, and the questions the
team still needs to answer. It is the file to review in the pull request.

---

## 1. Role boundary

The Knowledge Engine owns: ingestion APIs, validation, screen identity, SQLite
persistence, the app map, journeys, design analysis, the Knowledge Pack, and
stability comparison.

It does **not** own: emulator control, screenshot capture, UI-tree dumping,
action generation, exploration policy, or any dashboard/rebuild UI. It talks
HTTP and reads files off disk; nothing else.

---

## 2. Assumptions made (please confirm)

Each of these was a gap in the brief. The choice made is listed with the reason
so it can be overridden cheaply.

| # | Assumption | Why | Cost to change |
| --- | --- | --- | --- |
| A1 | `scan_id` defaults to `scan_000001` when a client omits it | Shared `screen_id` is only unique "within a controller session", so multiple scans need a namespace. Defaulting keeps Pallavi's current payload valid unchanged. | Low — one constant |
| A2 | Screen identity is decided by fingerprint, not by the controller's `screen_id` | Brief rule 4/5. A reused id would silently merge two different screens. | Low |
| A3 | Deduplication uses the **exact** fingerprint (text-sensitive) | Reliable and testable first version; over-merging is worse than over-splitting. Structural fingerprint is stored and ready. | Low — swap the lookup column |
| A4 | `screen_id` numbering is per-scan, starting at 1 | Matches the shared pattern `^screen_[0-9]{6}$` exactly | Medium |
| A5 | Elements are deduplicated within a screen by structural signature, not by `element_id` | The controller may renumber elements between visits | Low |
| A6 | `action_type` is validated as a free string; unknown values are stored with a warning | The shared action schema defines no enum | Low |
| A7 | The Knowledge Pack extension lives in a new file, `knowledge_pack.v0_2.schema.json` | Brief §6: do not silently change shared schemas | — |
| A8 | Design analysis reads screenshots from this service's own filesystem | No transport for images was specified | Medium — would need upload or object storage |

---

## 3. Open questions for the team

1. **Screenshot transport.** Does the Knowledge Engine share a volume with the
   controller, or should `POST /observations` accept a base64 image? Today it
   resolves `screenshot_path` against `KNOWLEDGE_MEDIA_ROOT`; if the file is
   absent, analysis degrades with a warning instead of failing.
2. **Who owns transitions?** Deekshitha knows source → action → target. If she
   sends both screen ids on `POST /actions`, edges appear automatically. If not,
   somebody must call `POST /transitions`. This needs to be decided, not assumed.
3. **Scan lifecycle.** Should there be an explicit `POST /scans` to open a run,
   or is the implicit `scan_id` on each payload enough?
4. **Knowledge Pack approval.** The extended fields are provisional. Suma should
   review `schemas/knowledge_pack.v0_2.schema.json` before building against it.
5. **Dynamic screens.** Screens with volatile text (clocks, feeds) will split
   under exact fingerprinting. Switch to structural matching, or leave it?

---

## 4. Database design

Eight tables: `scans`, `screens`, `observations`, `elements`, `actions`,
`transitions`, `journeys`, `design_language`, `knowledge_packs`.

Key decisions:

- **Composite primary keys** `(scan_id, screen_id)` etc. keep scans isolated
  while preserving the shared six-digit id format.
- **`UNIQUE (scan_id, fingerprint)` on `screens`** is what actually enforces
  deduplication; the application logic and the database agree.
- **`UNIQUE (scan_id, screen_id, element_signature)` on `elements`** guarantees
  the pack never carries duplicate elements within a screen.
- **Indexes** on `observation_id`, `screen_id`, `fingerprint`,
  `structural_fingerprint`, `action_id`, `source_screen_id`, `target_screen_id`.
- **`raw_json` columns** keep the original payloads, so unknown fields sent by
  teammates are never lost even though they are not modelled as columns.
- **WAL + `BEGIN IMMEDIATE`** gives durable writes across restarts and makes the
  screen-id counter safe under concurrency.

Hand-written SQL was chosen over SQLAlchemy to avoid adding a dependency for a
schema this small. `models.py` + `repositories.py` are the only files that would
change if the team later standardises on an ORM.

---

## 5. Why the core modules avoid Pydantic and FastAPI

`fingerprint`, `graph_builder`, `journey_builder`, `design_analyzer`,
`stability_checker` and `repositories` operate on plain dicts. They can be
imported, tested, and reused (for example by a CLI or by Suma's rebuild step)
without an HTTP stack. `api.py` is the only file that knows about FastAPI, and
`schemas.py` is the only one that knows about Pydantic.

---

## 6. Test strategy

Roughly 90 tests across eight files.

| File | Covers |
| --- | --- |
| `test_models.py` | Valid/invalid observations, bounds ordering, optional fields, unknown-field preservation |
| `test_fingerprint.py` | Determinism, id-independence, normalisation, order-independence |
| `test_screen_manager.py` | Creation, reuse, counter increments, untrusted `screen_id`, persistence |
| `test_graph_builder.py` | Nodes, edges, isolates, cycles, unknown targets, deterministic export |
| `test_journey_builder.py` | Shortest paths, no-path, cycle protection, length and count caps |
| `test_design_analyzer.py` | Missing/corrupt screenshots, determinism, confidence, unsupported properties stay empty |
| `test_knowledge_pack.py` | Required fields, determinism, no duplicate screens, statistics, warnings |
| `test_stability_checker.py` | Identical/added/removed/changed screens |
| `test_api.py` | Every endpoint plus invalid-request handling and scan isolation |

Every test that touches storage uses the `temp_db` fixture, which points
`KNOWLEDGE_DB_PATH` at a `tmp_path` file. No test writes to the real database.

---

## 7. Things deliberately not done

- No LLM calls, no inferred semantics, no "AI reasoning" dressed up as analysis.
  Journey names come from literal element text or fall back to screen numbers.
- No invented screens or transitions.
- No claim of exact font or corner radius from pixels.
- No frontend code.
- No edits to other members' files or to the approved shared schemas.
