"""Pydantic v2 request/response models.

These mirror the shared contracts in ``schemas/*.json``. Where the shared
schema says ``additionalProperties: true`` we set ``extra="allow"`` so unknown
fields from Pallavi/Deekshitha survive round-tripping instead of being dropped.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .config import SCHEMA_VERSION

SCREEN_ID_PATTERN = r"^screen_[0-9]{6}$"

#: Action types we currently understand. The shared action schema does NOT
#: define an enum, so we validate as a free string and only *warn* on unknown
#: values. Adding a type here must not require an API change.
KNOWN_ACTION_TYPES = (
    "tap",
    "type",
    "swipe",
    "scroll",
    "back",
    "long_press",
    "wait",
    "launch",
)


class Base(BaseModel):
    """Common config: allow unknown fields, strip whitespace on strings."""

    model_config = ConfigDict(extra="allow", str_strip_whitespace=True)


class Bounds(BaseModel):
    """Android pixel bounds. All four values are required integers."""

    model_config = ConfigDict(extra="forbid")

    left: int
    top: int
    right: int
    bottom: int

    @model_validator(mode="after")
    def _check_ordering(self) -> "Bounds":
        if self.left > self.right:
            raise ValueError("bounds.left must be <= bounds.right")
        if self.top > self.bottom:
            raise ValueError("bounds.top must be <= bounds.bottom")
        return self

    @property
    def width(self) -> int:
        return self.right - self.left

    @property
    def height(self) -> int:
        return self.bottom - self.top

    @property
    def area(self) -> int:
        return self.width * self.height


class Element(Base):
    """One node of the UI hierarchy, as sent by the Android controller."""

    element_id: str | None = None
    type: str | None = None
    text: str | None = None
    content_description: str | None = None
    resource_id: str | None = None
    clickable: bool = False
    enabled: bool = True
    scrollable: bool = False
    bounds: Bounds | None = None


class Observation(Base):
    """A single captured screen state."""

    observation_id: str = Field(min_length=1)
    screen_id: str | None = None
    timestamp: datetime | None = None
    package_name: str | None = None
    activity: str | None = None
    screenshot_path: str | None = None
    ui_tree_path: str | None = None
    elements: list[Element] = Field(default_factory=list)
    scan_id: str | None = None

    @field_validator("screen_id")
    @classmethod
    def _screen_id_shape(cls, value: str | None) -> str | None:
        """The controller's screen_id is advisory only, but if present it must
        still match the shared pattern so we catch contract drift early."""
        import re

        if value is not None and not re.match(SCREEN_ID_PATTERN, value):
            raise ValueError(f"screen_id must match {SCREEN_ID_PATTERN}")
        return value


class Action(Base):
    """An action the exploration agent performed (or intends to perform)."""

    action_id: str = Field(min_length=1)
    action_type: str = Field(min_length=1)
    element_id: str | None = None
    bounds: Bounds | None = None
    # Forward-compatible optional fields. Deekshitha can start sending these
    # at any time without an API version bump.
    source_screen_id: str | None = None
    target_screen_id: str | None = None
    timestamp: datetime | None = None
    result: str | None = None
    success: bool | None = None
    metadata: dict[str, Any] | None = None
    scan_id: str | None = None


class TransitionCreate(Base):
    """Explicit edge creation. Both endpoints are mandatory - we never guess."""

    source_screen_id: str
    target_screen_id: str
    action_id: str | None = None
    action_type: str | None = None
    element_id: str | None = None
    success: bool | None = None
    metadata: dict[str, Any] | None = None
    scan_id: str | None = None


class ScreenOut(Base):
    """Screen as returned by the API."""

    screen_id: str
    package_name: str | None = None
    activity: str | None = None
    screenshot_path: str | None = None
    ui_tree_path: str | None = None
    fingerprint: str | None = None
    structural_fingerprint: str | None = None
    element_count: int = 0
    elements: list[Element] = Field(default_factory=list)
    first_seen_observation_id: str | None = None
    observation_count: int = 0
    scan_id: str | None = None
    metadata: dict[str, Any] | None = None


class ObservationResponse(Base):
    observation_id: str
    screen: ScreenOut
    created: bool = Field(description="True when this observation produced a new screen.")
    message: str = "Observation processed successfully"
    warnings: list[str] = Field(default_factory=list)


class ActionResponse(Base):
    action_id: str
    action_type: str
    stored: bool = True
    message: str = "Action processed successfully"
    warnings: list[str] = Field(default_factory=list)


class TransitionResponse(Base):
    transition_id: str
    source_screen_id: str
    target_screen_id: str
    action_id: str | None = None
    action_type: str | None = None
    message: str = "Transition created successfully"


class GraphNode(Base):
    id: str
    label: str
    package_name: str | None = None
    activity: str | None = None
    element_count: int = 0
    observation_count: int = 0


class GraphEdge(Base):
    source: str
    target: str
    action_id: str | None = None
    action_type: str | None = None
    element_id: str | None = None
    label: str | None = None


class AppMap(Base):
    nodes: list[GraphNode] = Field(default_factory=list)
    edges: list[GraphEdge] = Field(default_factory=list)
    statistics: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)


class Journey(Base):
    journey_id: str
    name: str
    start_screen_id: str
    end_screen_id: str
    screen_ids: list[str] = Field(default_factory=list)
    action_ids: list[str] = Field(default_factory=list)
    transition_ids: list[str] = Field(default_factory=list)
    length: int = 0
    kind: str = "shortest_path"
    metadata: dict[str, Any] | None = None


class DesignLanguage(Base):
    """Aggregated design evidence. Every field is best-effort.

    Fields we cannot extract reliably from a screenshot (font family, exact
    corner radius) are intentionally absent rather than guessed.
    """

    dominant_colors: list[str] = Field(default_factory=list)
    background_colors: list[str] = Field(default_factory=list)
    text_colors: list[str] = Field(default_factory=list)
    button_colors: list[str] = Field(default_factory=list)
    font_sizes: list[float] = Field(default_factory=list)
    corner_radius_estimates: list[float] = Field(default_factory=list)
    spacing_estimates: dict[str, Any] = Field(default_factory=dict)
    screen_dimensions: list[dict[str, int]] = Field(default_factory=list)
    screenshot_count: int = 0
    analyzed_count: int = 0
    confidence: float = 0.0
    analysis_warnings: list[str] = Field(default_factory=list)


class KnowledgePackRequest(Base):
    package_name: str | None = None
    scan_id: str | None = None
    save_to_disk: bool = True
    include_elements: bool = True


class KnowledgePack(Base):
    """Extended Knowledge Pack.

    PROVISIONAL: only ``pack_id`` and ``source_observation_ids`` are part of the
    approved shared contract today. Everything else is a Member 3 proposal
    (see schemas/knowledge_pack.v0_2.schema.json) pending team sign-off.
    """

    pack_id: str
    source_observation_ids: list[str] = Field(default_factory=list)
    schema_version: str = SCHEMA_VERSION
    generated_at: str | None = None
    scan_id: str | None = None
    app: dict[str, Any] = Field(default_factory=dict)
    screens: list[dict[str, Any]] = Field(default_factory=list)
    elements: list[dict[str, Any]] = Field(default_factory=list)
    actions: list[dict[str, Any]] = Field(default_factory=list)
    transitions: list[dict[str, Any]] = Field(default_factory=list)
    journeys: list[dict[str, Any]] = Field(default_factory=list)
    design_language: dict[str, Any] = Field(default_factory=dict)
    statistics: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)


class StabilityCompareRequest(Base):
    previous_scan_id: str
    current_scan_id: str


class ChangedScreen(Base):
    previous_screen_id: str
    current_screen_id: str
    similarity: float
    reason: str


class StabilityReport(Base):
    previous_scan_id: str
    current_scan_id: str
    previous_screen_count: int
    current_screen_count: int
    matched_screens: int
    fingerprint_matches: int
    added_screens: list[str] = Field(default_factory=list)
    removed_screens: list[str] = Field(default_factory=list)
    changed_screens: list[ChangedScreen] = Field(default_factory=list)
    stability_score: float = 0.0
    warnings: list[str] = Field(default_factory=list)


class HealthResponse(BaseModel):
    status: str = "ok"
    service: str = "knowledge-engine"
    schema_version: str = SCHEMA_VERSION


class ErrorResponse(BaseModel):
    error: str
    detail: str
    type: str
