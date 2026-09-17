# START HERE — Knowledge Engine drop-in (Member 3, Sneha)

## Important: I could not inspect your repository

Your instructions (§29) asked me to inspect `RevRag_AI/` before writing
anything. **No repository was uploaded to this conversation**, so there was
nothing to read — no existing `requirements.txt`, no `schemas/` folder, no
branch state. Everything here was therefore written as a **self-contained,
additive module** that assumes nothing about your existing layout.

Before merging, run the inspection yourself (commands in §2 below) and check the
conflict list in §3.

---

## 1. What's in this zip

```
knowledge/                       # the module (13 files + README)
tests/                           # 9 test files + conftest.py
data/sample/                     # example observation / action / transition JSON
data/output/.gitkeep
schemas/knowledge_pack.v0_2.schema.json   # NEW file — a proposal, not a replacement
docs/knowledge-engine.md         # design decisions, assumptions, open questions
.env.example
requirements-knowledge.txt
pytest.ini
GITIGNORE_ADDITIONS.txt
```

Nothing here overwrites a file that the brief says already exists. The only file
placed inside your shared `schemas/` folder is a **new** one with a new name.
`screen.schema.json`, `observation.schema.json`, `element.schema.json`,
`action.schema.json` and `knowledge_pack.schema.json` are untouched.

---

## 2. Inspect first (do this before copying anything in)

```bash
cd RevRag_AI
git status && git branch --show-current
git checkout member3/knowledge-engine     # or create it from main

ls -la
cat requirements.txt 2>/dev/null || cat pyproject.toml
ls schemas/
grep -rn "FastAPI(" --include=*.py .       # is there already an API service?
grep -rni "sqlalchemy\|sqlite3" --include=*.py --include=*.txt .
ls -d knowledge data tests docs 2>/dev/null
cat docker-compose.yml 2>/dev/null
```

---

## 3. Conflicts to check for, and what to do

| If you find... | Do this |
| --- | --- |
| An existing `knowledge/` folder | Diff file by file. Do **not** bulk-copy. |
| An existing `tests/` folder | Copy only the `test_*.py` files. If `conftest.py` already exists, **merge** the fixtures instead of overwriting. |
| An existing FastAPI app (e.g. `app/main.py`) | Either run this as a second service on its own port, or mount it: `main_app.mount("/knowledge", knowledge_app)` — or `include_router` after converting `api.py` to an `APIRouter`. Ask the team which they prefer. |
| The repo already uses SQLAlchemy | The repository layer is isolated in `models.py` + `repositories.py`; rewriting those two files is the whole migration. |
| A `requirements.txt` exists | **Append** the lines from `requirements-knowledge.txt`, don't replace. Watch for version conflicts on `pydantic` and `numpy`. |
| `schemas/*.json` differ from the versions quoted in your brief | The repo files win. Tell me what they say and I'll adjust `schemas.py`. |
| `.gitignore` exists | Append `GITIGNORE_ADDITIONS.txt`, don't replace. |
| Alembic is in use | Say so and I'll convert `models.py` DDL into a migration. |

---

## 4. Install and run

```bash
pip install -r requirements-knowledge.txt
cp .env.example .env
pytest tests -q
uvicorn knowledge.api:app --reload --port 8100
# then open http://localhost:8100/docs
```

---

## 5. Test results from my environment (read this honestly)

This container has **no network access**, so `fastapi`, `pydantic`, `httpx` and
`pytest` could not be installed. What I could and could not verify:

- **Verified — 66 tests passed, 0 failed** across `test_fingerprint.py`,
  `test_graph_builder.py`, `test_journey_builder.py`, `test_stability_checker.py`,
  `test_design_analyzer.py`, `test_screen_manager.py` and `test_knowledge_pack.py`,
  executed against real SQLite, real NetworkX and real OpenCV.
- **Not executed — `test_models.py` and `test_api.py`.** They need Pydantic and
  FastAPI. Every file compiles cleanly (`python -m py_compile`), but the
  Pydantic models and the HTTP layer have not been run.

So: **run `pytest tests -q` yourself first**, and send me any failures from those
two files. I'd expect at most small fixes there, not structural ones.

---

## 6. Suggested phase order

Phase 1 (foundation) through Phase 8 (docs) are all present in code form, but
review them in the brief's order and confirm each before moving on:

1. Phase 1–2 — `schemas.py`, `fingerprint.py`, `screen_manager.py`, `/health`,
   `POST /observations`, SQLite. **Review these first**; everything else builds on
   the screen-identity decision.
2. Phase 3–4 — actions, transitions, graph, journeys.
3. Phase 5–6 — design analysis, Knowledge Pack.
4. Phase 7–8 — stability, docs.

---

## 7. What I need from you next

1. The real contents of `schemas/*.json` from the repo.
2. Your `requirements.txt` / `pyproject.toml`.
3. Whether a FastAPI app already exists, and on which port.
4. Answers to the five open questions in `docs/knowledge-engine.md` §3 —
   especially how screenshots reach this service, and who creates transitions.
