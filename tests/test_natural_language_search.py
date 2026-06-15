from app.services.natural_language_search import interpret_natural_language_search


def test_interprets_vehicle_price_mileage_location_and_seller() -> None:
    result = interpret_natural_language_search(
        "2020 Honda Civic under $20k under 100k km Montreal private seller"
    )

    assert result.interpreted_filters["make"] == "Honda"
    assert result.interpreted_filters["model"] == "Civic"
    assert result.interpreted_filters["year_min"] == 2020
    assert result.interpreted_filters["price_max_cad"] == 20000
    assert result.interpreted_filters["mileage_max_km"] == 100000
    assert result.interpreted_filters["location_city"] == "Montreal"
    assert result.interpreted_filters["location_province"] == "QC"
    assert result.interpreted_filters["seller_type"] == "private"
    assert result.confidence > 0.7


def test_explicit_structured_filters_override_interpreted_values() -> None:
    result = interpret_natural_language_search(
        "2020 Honda Civic under $20k Montreal",
        {"make": "Toyota", "model": "Corolla", "location_city": "Toronto"},
    )

    assert result.interpreted_filters["make"] == "Honda"
    assert result.interpreted_filters["model"] == "Civic"
    assert result.applied_filters["make"] == "Toyota"
    assert result.applied_filters["model"] == "Corolla"
    assert result.applied_filters["location_city"] == "Toronto"
    assert result.applied_filters["price_max_cad"] == 20000


def test_interprets_year_ranges_and_newer_older_phrasing() -> None:
    range_result = interpret_natural_language_search("2018-2021 Toyota Corolla")
    newer_result = interpret_natural_language_search("2019 or newer Mazda CX-5")
    older_result = interpret_natural_language_search("2021 or older Ford Escape")

    assert range_result.interpreted_filters["year_min"] == 2018
    assert range_result.interpreted_filters["year_max"] == 2021
    assert newer_result.interpreted_filters["year_min"] == 2019
    assert newer_result.interpreted_filters["make"] == "Mazda"
    assert newer_result.interpreted_filters["model"] == "CX-5"
    assert older_result.interpreted_filters["year_max"] == 2021
