"""Unit tests for discover filter helpers on CreatorRepository."""

from app.repositories.creator_repo import _sanitize_search_term


def test_sanitize_strips_postgrest_breakers():
    assert _sanitize_search_term("  food,(delhi).%  ") == "food delhi"
    assert _sanitize_search_term("a&b*c") == "a b c"
