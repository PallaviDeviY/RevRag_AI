"""Exception hierarchy for the Knowledge Engine (Member 3)."""

from __future__ import annotations


class KnowledgeEngineError(Exception):
    """Base class for every error raised by the Knowledge Engine."""

    status_code: int = 500


class ValidationError(KnowledgeEngineError):
    """Input failed a semantic validation rule (beyond Pydantic typing)."""

    status_code = 422


class NotFoundError(KnowledgeEngineError):
    """A referenced entity (screen, action, pack...) does not exist."""

    status_code = 404


class ConflictError(KnowledgeEngineError):
    """The request conflicts with stored state (duplicate id, etc.)."""

    status_code = 409


class StorageError(KnowledgeEngineError):
    """SQLite failed in a way the caller cannot fix."""

    status_code = 500


class AnalysisError(KnowledgeEngineError):
    """Design analysis failed hard. Normally we degrade with warnings instead."""

    status_code = 500
