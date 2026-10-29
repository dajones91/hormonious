"""Recipe library search."""

import pytest

from core.search import matches, search_text


def find(query, recipes, catalogue):
    return {r.slug for r in recipes if matches(search_text(r, catalogue), query)}


def test_title_cuisine_and_tags(recipes, catalogue):
    assert "thai-green-chicken-curry" in find("thai", recipes, catalogue)
    assert "turkey-chilli" in find("CHILLI", recipes, catalogue)  # case doesn't matter
    assert find("weekend special", recipes, catalogue) == {r.slug for r in recipes if r.tier == "weekend"}
    assert "chicken-souvlaki" in find("good-cold", recipes, catalogue)


def test_ingredients_including_swap_options(recipes, catalogue):
    assert find("butter beans", recipes, catalogue) >= {"tuscan-chicken", "steak-chimichurri", "chicken-piri-piri"}
    assert "turkey-lentil-bolognese" in find("lentil pasta", recipes, catalogue)  # a swap option


def test_every_word_must_match(recipes, catalogue):
    both = find("chicken rice", recipes, catalogue)
    assert both and all("chicken" in search_text(r, catalogue) and "rice" in search_text(r, catalogue)
                        for r in recipes if r.slug in both)
    assert "turkey-chilli" not in both


def test_empty_query_matches_everything(recipes, catalogue):
    assert find("", recipes, catalogue) == {r.slug for r in recipes}
    assert find("  ,  ", recipes, catalogue) == {r.slug for r in recipes}


@pytest.mark.parametrize("query", ["salmon", "zzz", "chicken salmon"])
def test_no_matches(query, recipes, catalogue):
    assert find(query, recipes, catalogue) == set()
