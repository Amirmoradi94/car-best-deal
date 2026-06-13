from enum import StrEnum


class SellerType(StrEnum):
    PRIVATE = "private"
    DEALER = "dealer"
    AUCTION = "auction"
    UNKNOWN = "unknown"


class OpportunityStage(StrEnum):
    NEW = "new"
    CANDIDATE = "candidate"
    NEEDS_DATA = "needs_data"
    CONTACT_SELLER = "contact_seller"
    READY_TO_VISIT = "ready_to_visit"
    VISITED = "visited"
    OFFER_MADE = "offer_made"
    BOUGHT = "bought"
    PASSED = "passed"


class ReportStatus(StrEnum):
    PRELIMINARY = "preliminary"
    PARTIAL = "partial"
    FULL = "full"
    STALE = "stale"
    FAILED = "failed"


class Recommendation(StrEnum):
    BUY = "buy"
    BUY_ONLY_CHEAP = "buy_only_cheap"
    PASS = "pass"
    NEEDS_MORE_DATA = "needs_more_data"


class ConfidenceLevel(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    UNKNOWN = "unknown"


class RiskTolerance(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"

