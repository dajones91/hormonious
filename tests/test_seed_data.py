"""Checks on the seed library and the database round trip."""

from collections import Counter

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from core.nutrition import Nutrition, base_per_portion, for_grams
from db.repo import get_catalogue, get_exclusion_rules, get_recipes, reset_and_seed


def test_library_size_and_mix(recipes):
    tiers = Counter(r.tier for r in recipes)
    assert len(recipes) == 20
    assert tiers["weeknight"] >= 14 and tiers["weekend"] >= 3


def test_slugs_unique(recipes):
    assert len({r.slug for r in recipes}) == len(recipes)


def test_every_ingredient_exists(catalogue, recipes):
    missing = {r.slug: sorted(r.ingredient_keys() - catalogue.keys()) for r in recipes
               if r.ingredient_keys() - catalogue.keys()}
    assert missing == {}


def test_time_limits(recipes):
    for r in recipes:
        limit = 45 if r.tier == "weeknight" else 90
        assert r.total_min <= limit, r.slug


def test_weeknights_are_lunchbox_friendly(recipes):
    """Weeknight cooks make 4 portions, 2 of which become next-day lunches."""
    assert [r.slug for r in recipes if r.tier == "weeknight" and "lunchbox-friendly" not in r.tags] == []
    assert all(r.servings == 4 for r in recipes)


def test_every_recipe_has_reheat_note(recipes):
    assert [r.slug for r in recipes if not r.reheat_note] == []


def test_most_recipes_have_a_flexible_carb_with_a_lower_carb_swap(catalogue, recipes):
    for r in recipes:
        for comp in r.flexible:
            if comp.component == "carb":
                assert len(comp.options) >= 2, r.slug
    assert sum(1 for r in recipes if not r.flexible) >= 1  # at least one "standard portion" recipe


def test_refined_carbs_always_have_a_swap(catalogue, recipes):
    for r in recipes:
        for comp in r.flexible:
            if any("refined_carb" in catalogue[o.ingredient].flags for o in comp.options):
                assert any(catalogue[o.ingredient].gi == "low" for o in comp.options), r.slug


def test_every_recipe_has_a_healthy_fat_and_veg(catalogue, recipes):
    for r in recipes:
        flags = set().union(*(catalogue[i.ingredient].flags for i in r.shared))
        assert {"healthy_fat", "vegetable", "protein"} <= flags, r.slug


def test_nutrition_maths():
    chicken = {"kcal": 106, "protein": 24.0, "carbs": 0, "sugars": 0, "fibre": 0, "fat": 1.1}
    from core.schema import Ingredient
    ing = Ingredient(key="c", name="Chicken", aisle="x", state="raw", **chicken)
    assert for_grams(ing, 250) == Nutrition(265, 60, 0, 0, 0, 2.75)
    assert Nutrition(1, 2, 3, 4, 5, 6) + Nutrition(1, 1, 1, 1, 1, 1) == Nutrition(2, 3, 4, 5, 6, 7)
    assert Nutrition(434, 35.4, 0, 0, 7.6, 12.5).rounded() == Nutrition(430, 35, 0, 0, 8, 12)


def test_base_protein_supports_35g_on_an_even_split(catalogue, recipes):
    """The shared base alone should give each person 35 g protein at 50/50,
    so even a zero-protein swap (e.g. cauliflower rice) keeps the plate on target."""
    low = {r.slug: round(base_per_portion(r, catalogue).protein) for r in recipes
           if base_per_portion(r, catalogue).protein < 35}
    assert low == {}


@pytest.fixture
def db_session():
    with Session(create_engine("sqlite://")) as session:  # in-memory, thrown away afterwards
        yield session


def test_database_round_trip(db_session, catalogue, recipes, rules):
    counts = reset_and_seed(db_session)
    assert counts == {"ingredients": len(catalogue), "people": 2, "recipes": len(recipes)}
    assert get_catalogue(db_session) == catalogue
    assert get_recipes(db_session) == recipes
    assert sorted(get_exclusion_rules(db_session), key=repr) == sorted(rules, key=repr)
