from app.domain.enums import SellerType
from app.domain.models import ComparableListing, ListingSnapshot, VehicleProfile
from app.services.pricing import comparable_similarity, weighted_percentile


def test_weighted_percentile_returns_weighted_median() -> None:
    values = [(100.0, 1.0), (200.0, 10.0), (300.0, 1.0)]

    assert weighted_percentile(values, 0.5) == 200.0


def test_comparable_similarity_rewards_close_match() -> None:
    target = ListingSnapshot(
        id="target",
        source_name="kijiji",
        url="https://example.test",
        vehicle=VehicleProfile(
            year=2020,
            make="Honda",
            model="Civic",
            trim="EX",
            mileage_km=85000,
            drivetrain="FWD",
            body_style="Sedan",
        ),
        asking_price_cad=14500,
        location_city="Montreal",
        seller_type=SellerType.PRIVATE,
    )
    comparable = ComparableListing(
        id="comp",
        source_name="autotrader",
        url="https://example.test/comp",
        year=2020,
        make="Honda",
        model="Civic",
        trim="EX",
        mileage_km=87000,
        asking_price_cad=18900,
        location_city="Montreal",
        seller_type=SellerType.PRIVATE,
        certified=False,
        drivetrain="FWD",
        body_style="Sedan",
    )

    assert comparable_similarity(target, comparable) >= 0.85

