from middleware.clients.nocodb_client import (
    build_updated_since_filter,
    normalize_nocodb_datetime,
)


def test_normalize_strips_timezone_offset():
    assert normalize_nocodb_datetime("2026-11-12 19:55:33+00:00") == "2026-11-12 19:55:33"
    assert normalize_nocodb_datetime("2026-11-12T19:55:33Z") == "2026-11-12 19:55:33"
    assert normalize_nocodb_datetime(None) is None


def test_incremental_filter_uses_exact_date():
    clause = build_updated_since_filter("2026-11-12 19:55:33+00:00")
    assert clause == "(leafnet_updated_at,gt,exactDate,2026-11-12 19:55:33)"
    assert build_updated_since_filter(None) is None
    assert build_updated_since_filter("") is None
