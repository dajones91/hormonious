"""Tests for the exclusion filter, including ingredient variants and exceptions."""

import pytest

from core.exclusions import ExclusionRule, check_name, check_recipe, is_allowed, is_vegetarian
from core.families import KEYWORD_RULES, ancestors, classify_name
from core.schema import Recipe


def people_excluding(name, rules):
    return sorted({hit.person for hit in check_name(name, rules)})


# --- Jade: no fish or shellfish, with three exceptions -----------------------

@pytest.mark.parametrize("name", [
    "Salmon fillets", "smoked salmon", "Cod fillets", "tinned tuna", "Haddock", "sea bass fillets",
    "mackerel", "sardines", "trout", "King prawns", "cooked shrimp", "crab meat", "Mussels",
    "squid rings", "calamari", "scallops", "anchovy fillets", "anchovies", "Caesar dressing",
    "fresh oysters", "fishcakes", "white fish", "mixed seafood",
])
def test_seafood_excluded_for_jade(name, rules):
    assert people_excluding(name, rules) == ["jade"]


@pytest.mark.parametrize("name", [
    "Fish sauce", "Thai fish sauce", "nam pla", "shrimp paste", "breaded cod fillets",
    "Battered cod", "Cod loin for breading", "oyster sauce", "Worcestershire sauce",
])
def test_seafood_exceptions_are_allowed(name, rules):
    assert check_name(name, rules) == []


def test_exception_does_not_cover_other_seafood_in_the_same_name(rules):
    # breaded cod is fine, but the prawns are not
    hits = check_name("breaded cod and prawns", rules)
    assert [(h.person, h.family) for h in hits] == [("jade", "prawn")]


def test_plain_cod_is_still_excluded(rules):
    assert people_excluding("cod loin", rules) == ["jade"]


# --- Jade: no mushrooms in any form ------------------------------------------

@pytest.mark.parametrize("name", [
    "Chestnut mushrooms", "mushroom", "dried porcini", "shiitake", "portobello mushrooms",
    "mushroom stock cube", "mushroom ketchup", "oyster mushrooms", "truffle oil",
])
def test_mushrooms_excluded_for_jade(name, rules):
    assert people_excluding(name, rules) == ["jade"]


def test_oyster_mushrooms_count_as_mushroom_not_shellfish():
    assert classify_name("oyster mushrooms") == {"mushroom"}


# --- Household: no meat substitutes, no paneer -------------------------------------

@pytest.mark.parametrize("name", [
    "Quorn mince", "Quorn pieces", "mycoprotein", "seitan", "soya mince", "TVP",
    "textured vegetable protein", "plant-based mince", "vegan sausages", "meat-free burgers",
    "vegetarian chicken pieces", "vegan fish fingers", "Paneer", "paneer cubes",
])
def test_meat_substitutes_and_paneer_excluded_for_both(name, rules):
    assert people_excluding(name, rules) == ["dale", "jade"]


def test_meat_substitute_is_not_read_as_meat_or_fish():
    assert classify_name("vegan sausages") == {"meat_substitute"}
    assert classify_name("vegan fish fingers") == {"meat_substitute"}
    assert classify_name("Quorn mince") == {"mycoprotein"}


@pytest.mark.parametrize("name", ["Firm tofu", "edamame beans", "red lentils", "Greek yoghurt", "halloumi"])
def test_real_foods_are_not_meat_substitutes(name, rules):
    assert check_name(name, rules) == []


# --- Dale: no whole pieces of fruit; juice and zest are fine ------------------

@pytest.mark.parametrize("name", [
    "Mango", "diced mango", "raisins", "sultanas", "dried apricots", "pomegranate seeds",
    "cherries", "strawberries", "blueberries", "apple", "sliced pears", "pineapple chunks",
    "Medjool dates", "dried cranberries", "mango chutney", "orange segments", "banana",
    "preserved lemons",
])
def test_whole_fruit_excluded_for_dale(name, rules):
    assert people_excluding(name, rules) == ["dale"]


@pytest.mark.parametrize("name", [
    "Lemon juice", "lime juice", "lemon zest", "orange zest", "juice of 1 lime", "apple juice",
    "Apple cider vinegar", "Cherry tomatoes", "plum tomatoes", "red pepper", "orange pepper",
    "kaffir lime leaves", "Avocado", "light coconut milk", "olives", "lemon", "lemon slices to garnish",
    "grapeseed oil", "red lentils", "tomatoes",
])
def test_savoury_and_juice_allowed_for_dale(name, rules):
    assert check_name(name, rules) == []


# --- How the rules combine -----------------------------------------------------

def test_family_chain():
    assert ancestors("salmon") == ["salmon", "oily_fish", "fish", "seafood"]
    assert ancestors("breaded_cod") == ["breaded_cod", "cod", "white_fish", "fish", "seafood"]


def test_shared_meal_rule_either_person_excludes(catalogue, recipes, rules):
    """A recipe is out if *anyone* excludes an ingredient in it, even as a swap option."""
    base = next(r for r in recipes if r.slug == "chicken-souvlaki")
    with_mango = Recipe(**{**base.model_dump(), "slug": "mango-test",
                           "shared": [*base.model_dump()["shared"], {"ingredient": "mango", "grams": 100}]})
    hits = check_recipe(with_mango, catalogue, rules)
    assert [(h.person, h.family) for h in hits] == [("dale", "fresh_fruit")]
    assert not is_allowed(with_mango, catalogue, rules)

    swap_data = base.model_dump()
    swap_data["slug"] = "mushroom-swap-test"
    swap_data["flexible"][0]["options"].append(
        {"ingredient": "chestnut_mushrooms", "standard_grams": 100, "max_grams": 200})
    assert [h.person for h in check_recipe(Recipe(**swap_data), catalogue, rules)] == ["jade"]


def test_rules_are_per_person():
    only_dale = [ExclusionRule("dale", "whole_fruit")]
    assert check_name("King prawns", only_dale) == []
    assert [h.person for h in check_name("mango", only_dale)] == ["dale"]


def test_fish_sauce_recipe_is_allowed_but_not_vegetarian(catalogue, recipes, rules):
    curry = next(r for r in recipes if r.slug == "thai-green-chicken-curry")
    assert "fish_sauce" in curry.ingredient_keys()
    assert is_allowed(curry, catalogue, rules)
    assert not is_vegetarian(curry, catalogue)


def test_breaded_cod_recipe_is_allowed(catalogue, recipes, rules):
    cod = next(r for r in recipes if r.slug == "crispy-cod-chips-peas")
    assert is_allowed(cod, catalogue, rules)


# --- Data consistency ----------------------------------------------------------

def test_ingredient_tags_match_keyword_safety_net(catalogue):
    """Every ingredient's families should match what its name suggests, so the
    table and the keyword net never disagree."""
    mismatches = {k: (sorted(i.families), sorted(classify_name(i.name)))
                  for k, i in catalogue.items() if i.families != classify_name(i.name)}
    assert mismatches == {}


def test_every_family_in_rules_is_known():
    known = set(ancestors_all())
    for family, _ in KEYWORD_RULES:
        if family is not None:
            assert family in known, family


def ancestors_all():
    from core.families import PARENTS
    return set(PARENTS) | set(PARENTS.values()) | {"fruit_juice", "paneer"}


def test_all_seed_recipes_pass_exclusions(catalogue, recipes, rules):
    failing = {r.slug: [str(h) for h in check_recipe(r, catalogue, rules)]
               for r in recipes if not is_allowed(r, catalogue, rules)}
    assert failing == {}
