from app.scraping.errors import SourceFailureDetail, SourceFailureReason, SourceScrapingError


def test_source_scraping_error_carries_structured_failure() -> None:
    failure = SourceFailureDetail(
        source_name="kijiji",
        reason=SourceFailureReason.CREDENTIALS_MISSING,
        message="missing key",
    )
    error = SourceScrapingError(failure)

    assert error.failure.reason == SourceFailureReason.CREDENTIALS_MISSING
    assert str(error) == "missing key"

