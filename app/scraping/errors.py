from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class SourceFailureReason(StrEnum):
    BLOCKED = "blocked"
    TIMEOUT = "timeout"
    PARSING_FAILED = "parsing_failed"
    NO_RESULTS = "no_results"
    SOURCE_LAYOUT_CHANGED = "source_layout_changed"
    SOURCE_UNAVAILABLE = "source_unavailable"
    CREDENTIALS_MISSING = "credentials_missing"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class SourceFailureDetail:
    source_name: str
    reason: SourceFailureReason
    url: str | None = None
    message: str | None = None
    retryable: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


class SourceScrapingError(RuntimeError):
    def __init__(self, failure: SourceFailureDetail) -> None:
        self.failure = failure
        super().__init__(failure.message or failure.reason.value)
