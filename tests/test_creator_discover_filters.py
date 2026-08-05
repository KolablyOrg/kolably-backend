"""Unit tests for discover filter helpers on CreatorRepository."""

from app.repositories.creator_repo import _city_match_terms, _sanitize_search_term


def test_sanitize_strips_postgrest_breakers():
    assert _sanitize_search_term("  food,(delhi).%  ") == "food delhi"
    assert _sanitize_search_term("a&b*c") == "a b c"


def test_city_match_terms_expands_delhi_ncr():
    terms = _city_match_terms("Delhi NCR")
    assert "Delhi" in terms
    assert "New Delhi" in terms
    assert "Noida" in terms


def test_city_match_terms_south_delhi_covers_live_spellings():
    terms = _city_match_terms("South Delhi")
    assert "South Delhi" in terms
    assert "Delhi" in terms
    assert "New Delhi" in terms


def test_city_match_terms_mumbai_and_bengaluru_aliases():
    assert "Bangalore" in _city_match_terms("Bengaluru")
    assert "Bombay" in _city_match_terms("Mumbai")


def test_city_match_terms_unknown_city_passthrough():
    assert _city_match_terms("Pune") == ["Pune"]
    assert _city_match_terms("  ") == []
