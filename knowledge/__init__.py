"""RevRag AI - Knowledge Engine (Member 3: Sneha).

Turns observations and actions from the Android controller and exploration
agent into a deduplicated screen model, an app map, journeys, design language,
and an exportable Knowledge Pack.
"""

from .config import Settings, get_settings
from .exceptions import (
    ConflictError,
    KnowledgeEngineError,
    NotFoundError,
    StorageError,
    ValidationError,
)

__version__ = "0.2.0"

__all__ = [
    "Settings",
    "get_settings",
    "KnowledgeEngineError",
    "ValidationError",
    "NotFoundError",
    "ConflictError",
    "StorageError",
    "__version__",
]
