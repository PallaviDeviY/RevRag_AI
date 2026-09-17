"""FastAPI application for the Knowledge Engine (Member 3).

Run locally::

    uvicorn knowledge.api:app --reload --port 8100

Design notes
------------
* Every endpoint is scoped by ``scan_id``. It defaults to ``scan_000001`` so the
  simplest possible client (Pallavi POSTing observations with no extra fields)
  keeps working, while repeat scans stay isolated from each other.
* Business logic lives in the other modules; this file only does HTTP.
"""

from __future__ import annotations

import logging
from typing import Any

from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Query, Request
from fastapi.responses import JSONResponse

from . import repositories as repo
from .config import DEFAULT_SCAN_ID, get_settings
from .database import init_db, session, transaction
from .exceptions import KnowledgeEngineError, NotFoundError
from .graph_builder import build_graph, graph_statistics, skipped_transitions, to_json
from .journey_builder import discover_journeys, element_text_index
from .knowledge_pack import generate_and_store
from .schemas import (
    Action,
    ActionResponse,
    AppMap,
    HealthResponse,
    KnowledgePack,
    KnowledgePackRequest,
    Observation,
    ObservationResponse,
    ScreenOut,
    StabilityCompareRequest,
    StabilityReport,
    TransitionCreate,
    TransitionResponse,
)
from .schemas import KNOWN_ACTION_TYPES, Journey
from .screen_manager import ScreenManager
from .stability_checker import compare_scans

logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(_: FastAPI):
    """Configure logging, create directories, and initialise SQLite on boot."""
    settings = get_settings()
    logging.basicConfig(level=settings.log_level)
    settings.ensure_dirs()
    init_db()
    yield


app = FastAPI(
    title="RevRag AI - Knowledge Engine",
    description=(
        "Member 3 (Sneha). Ingests observations and actions from the Android "
        "controller and exploration agent, builds screen identity, the app map, "
        "journeys and design language, and exports a Knowledge Pack."
    ),
    version="0.2.0",
    lifespan=lifespan,
)


@app.exception_handler(KnowledgeEngineError)
async def _domain_error_handler(_: Request, exc: KnowledgeEngineError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": exc.__class__.__name__, "detail": str(exc), "type": "knowledge_engine"},
    )


def scan_id_param(
    scan_id: str = Query(
        DEFAULT_SCAN_ID, description="Isolates one exploration run. Defaults to scan_000001."
    )
) -> str:
    return scan_id


# --------------------------------------------------------------------------
# health
# --------------------------------------------------------------------------

@app.get("/health", response_model=HealthResponse, tags=["system"])
def health() -> HealthResponse:
    """Liveness probe used by the team's docker-compose stack."""
    return HealthResponse()


# --------------------------------------------------------------------------
# ingestion
# --------------------------------------------------------------------------

@app.post("/observations", response_model=ObservationResponse, tags=["ingestion"])
def ingest_observation(observation: Observation) -> ObservationResponse:
    """Ingest one observation from Pallavi's Android controller.

    The supplied ``screen_id`` is recorded but NOT trusted for deduplication -
    screen identity is decided by the Knowledge Engine's fingerprint.
    """
    scan_id = observation.scan_id or DEFAULT_SCAN_ID
    payload = observation.model_dump(mode="json")
    manager = ScreenManager(scan_id)
    with transaction() as conn:
        screen, created, warnings = manager.process_observation(conn, payload)
    return ObservationResponse(
        observation_id=observation.observation_id,
        screen=ScreenOut(**{**screen, "scan_id": scan_id}),
        created=created,
        warnings=warnings,
    )


@app.post("/actions", response_model=ActionResponse, tags=["ingestion"])
def ingest_action(action: Action) -> ActionResponse:
    """Ingest one action from Deekshitha's exploration agent.

    If both ``source_screen_id`` and ``target_screen_id`` are present AND both
    screens exist, a transition is created as a convenience. A missing target is
    never invented.
    """
    scan_id = action.scan_id or DEFAULT_SCAN_ID
    payload = action.model_dump(mode="json")
    warnings: list[str] = []
    if action.action_type not in KNOWN_ACTION_TYPES:
        warnings.append(
            f"action_type '{action.action_type}' is not in the documented set "
            f"{list(KNOWN_ACTION_TYPES)}; stored as-is."
        )

    with transaction() as conn:
        repo.ensure_scan(conn, scan_id)
        repo.upsert_action(conn, scan_id=scan_id, action=payload)

        if action.source_screen_id and action.target_screen_id:
            missing = [
                sid
                for sid in (action.source_screen_id, action.target_screen_id)
                if repo.get_screen(conn, scan_id, sid) is None
            ]
            if missing:
                warnings.append(
                    f"No transition created: unknown screen(s) {missing}. "
                    "Ingest those observations first, or POST /transitions later."
                )
            else:
                repo.insert_transition(
                    conn,
                    scan_id=scan_id,
                    source_screen_id=action.source_screen_id,
                    target_screen_id=action.target_screen_id,
                    action_id=action.action_id,
                    action_type=action.action_type,
                    element_id=action.element_id,
                    success=action.success,
                )
        elif action.source_screen_id and not action.target_screen_id:
            warnings.append(
                "Action stored with a source screen but no target screen; "
                "no transition was created."
            )

    return ActionResponse(
        action_id=action.action_id, action_type=action.action_type, warnings=warnings
    )


@app.post("/transitions", response_model=TransitionResponse, tags=["ingestion"])
def create_transition(transition: TransitionCreate) -> TransitionResponse:
    """Create an explicit edge between two known screens."""
    scan_id = transition.scan_id or DEFAULT_SCAN_ID
    with transaction() as conn:
        repo.ensure_scan(conn, scan_id)
        for sid in (transition.source_screen_id, transition.target_screen_id):
            if repo.get_screen(conn, scan_id, sid) is None:
                raise NotFoundError(f"Screen '{sid}' does not exist in scan '{scan_id}'")
        transition_id = repo.insert_transition(
            conn,
            scan_id=scan_id,
            source_screen_id=transition.source_screen_id,
            target_screen_id=transition.target_screen_id,
            action_id=transition.action_id,
            action_type=transition.action_type,
            element_id=transition.element_id,
            success=transition.success,
            metadata=transition.metadata,
        )
    return TransitionResponse(
        transition_id=transition_id,
        source_screen_id=transition.source_screen_id,
        target_screen_id=transition.target_screen_id,
        action_id=transition.action_id,
        action_type=transition.action_type,
    )


# --------------------------------------------------------------------------
# reads
# --------------------------------------------------------------------------

@app.get("/screens", response_model=list[ScreenOut], tags=["knowledge"])
def list_screens(
    scan_id: str = Depends(scan_id_param),
    package_name: str | None = Query(None),
    include_elements: bool = Query(True),
) -> list[ScreenOut]:
    """List every deduplicated screen discovered in a scan."""
    with session() as conn:
        rows = repo.list_screens(conn, scan_id, package_name)
        screens = []
        for row in rows:
            screen = dict(row)
            screen["elements"] = (
                repo.list_elements(conn, scan_id, screen["screen_id"]) if include_elements else []
            )
            screens.append(ScreenOut(**{**screen, "scan_id": scan_id}))
    return screens


@app.get("/screens/{screen_id}", response_model=ScreenOut, tags=["knowledge"])
def get_screen(screen_id: str, scan_id: str = Depends(scan_id_param)) -> ScreenOut:
    """Fetch one screen with its elements."""
    with session() as conn:
        screen = repo.screen_with_elements(conn, scan_id, screen_id)
    if screen is None:
        raise NotFoundError(f"Screen '{screen_id}' not found in scan '{scan_id}'")
    return ScreenOut(**{**screen, "scan_id": scan_id})


@app.get("/app-map", response_model=AppMap, tags=["knowledge"])
def app_map(scan_id: str = Depends(scan_id_param)) -> AppMap:
    """Dashboard-friendly nodes/edges view of the app graph."""
    with session() as conn:
        screens = [
            {**dict(row), "elements": repo.list_elements(conn, scan_id, row["screen_id"])}
            for row in repo.list_screens(conn, scan_id)
        ]
        transitions = repo.list_transitions(conn, scan_id)
    graph = build_graph(screens, transitions)
    exported = to_json(graph)
    return AppMap(
        nodes=exported["nodes"],
        edges=exported["edges"],
        statistics=graph_statistics(graph),
        warnings=skipped_transitions(screens, transitions),
    )


@app.get("/journeys", response_model=list[Journey], tags=["knowledge"])
def journeys(
    scan_id: str = Depends(scan_id_param),
    refresh: bool = Query(True, description="Recompute from the current graph."),
) -> list[Journey]:
    """Discovered paths through the app.

    These are explorer-observed paths, not user-validated flows.
    """
    settings = get_settings()
    if not refresh:
        with session() as conn:
            stored = repo.list_journeys(conn, scan_id)
        return [Journey(**j) for j in stored]

    with transaction() as conn:
        screens = [
            {**dict(row), "elements": repo.list_elements(conn, scan_id, row["screen_id"])}
            for row in repo.list_screens(conn, scan_id)
        ]
        transitions = repo.list_transitions(conn, scan_id)
        graph = build_graph(screens, transitions)
        discovered = discover_journeys(
            graph,
            element_text_by_id=element_text_index(screens),
            max_length=settings.max_journey_length,
            max_journeys=settings.max_journeys,
        )
        stored = repo.replace_journeys(conn, scan_id=scan_id, journeys=discovered)
    return [Journey(**j) for j in stored]


# --------------------------------------------------------------------------
# knowledge pack
# --------------------------------------------------------------------------

@app.post("/knowledge-pack/generate", response_model=KnowledgePack, tags=["knowledge-pack"])
def generate_knowledge_pack(
    request: KnowledgePackRequest | None = None,
) -> KnowledgePack:
    """Build and persist a Knowledge Pack for Suma's dashboard.

    The body is optional: an empty POST generates a pack for the default scan.
    """
    request = request or KnowledgePackRequest()
    scan_id = request.scan_id or DEFAULT_SCAN_ID
    settings = get_settings()
    with transaction() as conn:
        repo.ensure_scan(conn, scan_id, request.package_name)
        pack = generate_and_store(
            conn,
            scan_id=scan_id,
            package_name=request.package_name,
            save_to_disk=request.save_to_disk,
            include_elements=request.include_elements,
            media_root=settings.media_root,
        )
    return KnowledgePack(**pack)


@app.get("/knowledge-pack/latest", response_model=KnowledgePack, tags=["knowledge-pack"])
def latest_knowledge_pack(
    scan_id: str | None = Query(None, description="Omit to get the newest pack of any scan.")
) -> KnowledgePack:
    """Return the most recently generated Knowledge Pack."""
    with session() as conn:
        pack = repo.latest_pack(conn, scan_id)
    if pack is None:
        raise NotFoundError(
            "No Knowledge Pack has been generated yet. POST /knowledge-pack/generate first."
        )
    return KnowledgePack(**pack)


# --------------------------------------------------------------------------
# stability
# --------------------------------------------------------------------------

@app.post("/stability/compare", response_model=StabilityReport, tags=["stability"])
def compare(request: StabilityCompareRequest) -> StabilityReport:
    """Compare two scans of the same app and score explorer repeatability."""
    with session() as conn:
        report = compare_scans(conn, request.previous_scan_id, request.current_scan_id)
    return StabilityReport(**report)


@app.get("/scans", response_model=list[dict[str, Any]], tags=["system"])
def scans() -> list[dict[str, Any]]:
    """List known scans, useful before calling /stability/compare."""
    with session() as conn:
        return repo.list_scans(conn)
