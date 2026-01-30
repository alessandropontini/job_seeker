from job_scout.normalize import (
    convert_to_eur,
    normalize_remote_level,
    parse_salary_range,
)


def test_normalize_remote_level():
    assert normalize_remote_level("Remote") == "full-remote"
    assert normalize_remote_level("Hybrid") == "hybrid"
    assert normalize_remote_level("On-site") == "onsite"
    assert normalize_remote_level("") == "unknown"


def test_parse_salary_range_with_currency():
    salary_min, salary_max, currency = parse_salary_range(
        "€80k-€95k", None
    )
    assert salary_min == 80000
    assert salary_max == 95000
    assert currency == "EUR"


def test_convert_to_eur():
    assert convert_to_eur(100000, "USD", {"USD": 0.9}) == 90000
