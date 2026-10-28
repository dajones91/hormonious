"""Shopping list: totals for 4 portions, merging, swaps, pack rounding, aisles and text export."""

import pytest

from core.cooking import amount_text, cook_base, cook_flex, pot_shares
from core.loaders import load_household
from core.portions import FlexChoice, MealTarget, base_shares, meals_for_portions, plan_plates
from core.shopping import (PlannedCook, ShoppingItem, as_text, build_list, choose_packs, group_by_aisle,
                           packs_text)


@pytest.fixture(scope="module")
def targets():
    h = load_household()
    return {p: {m: MealTarget(**t) for m, t in meals.items()} for p, meals in h["targets"].items()}


def cook(recipes, catalogue, targets, slug, portions=4, choices=None):
    r = next(x for x in recipes if x.slug == slug)
    plates = plan_plates(r, catalogue, targets, base_shares(r, "even", {}, targets), meals_for_portions(portions),
                         choices)
    return PlannedCook(r, portions, plates)


def by_key(items):
    return {i.key: i for i in items}


# --- Pack rounding ---------------------------------------------------------------------

@pytest.mark.parametrize("needed, sizes, expected", [
    (450, [500], [500]),
    (650, [300, 650, 1000], [650]),
    (700, [300, 650, 1000], [300, 300, 300]),  # 900 g is less over than a 1 kg pack
    (480, [240], [240, 240]),                 # two tins
    (481, [240], [240, 240, 240]),
    (1100, [500, 1000], [1000, 500]),
    (7, [6, 12], [12]),                       # 7 eggs -> a box of 12, not two 6s (same total, fewer packs)
    (0, [500], []),
    (120, [], [120]),                         # no pack sizes known: buy what's needed
])
def test_choose_packs(needed, sizes, expected):
    assert choose_packs(needed, sizes) == expected


def test_pack_text(catalogue):
    assert packs_text(catalogue["chicken_breast"], [650.0]) == "1 x 650 g pack"
    assert packs_text(catalogue["chickpeas"], [240.0, 240.0]) == "2 x 400 g tin"
    assert packs_text(catalogue["eggs"], [12.0]) == "1 x box of 12"
    assert packs_text(catalogue["chicken_breast"], [1000.0, 300.0]) == "1 x 1000 g pack + 1 x 300 g pack"


def test_loose_items_are_counted(catalogue):
    onions = ShoppingItem(catalogue["onion"], grams=320)  # 150 g each -> 3 onions
    assert onions.needed == 3 and onions.buy_text == "3 onions"
    lemons = ShoppingItem(catalogue["lemon_juice"], grams=45)  # 30 ml per lemon -> 2 lemons
    assert lemons.buy_text == "2 lemons"
    one = ShoppingItem(catalogue["avocado"], grams=130)
    assert one.buy_text == "1 avocado"


def test_needed_rounds_up(catalogue):
    assert ShoppingItem(catalogue["chicken_breast"], grams=649.2).needed == 650
    assert ShoppingItem(catalogue["onion"], grams=301).needed == 3  # just over 2 onions -> 3


# --- Building the list ----------------------------------------------------------------

def test_totals_for_four_portions_match_the_recipe(catalogue, recipes, targets):
    c = cook(recipes, catalogue, targets, "turkey-chilli")
    items = by_key(build_list([c], catalogue, set()))
    assert items["turkey_mince"].grams == pytest.approx(750)  # the base is cooked once for all 4
    assert items["chopped_tomatoes"].buy_text == "2 x 400 g tin"


def test_two_portions_halves_the_base(catalogue, recipes, targets):
    c = cook(recipes, catalogue, targets, "steak-chimichurri", portions=2)
    items = by_key(build_list([c], catalogue, set()))
    assert items["beef_sirloin"].grams == pytest.approx(400)
    assert len(c.plates) == 2  # dinner only


def test_flexible_amounts_come_from_each_plate(catalogue, recipes, targets):
    c = cook(recipes, catalogue, targets, "chicken-tikka-traybake")
    items = by_key(build_list([c], catalogue, set()))
    rice = sum(comp.grams for p in c.plates for comp in p.components if comp.ingredient.key == "brown_basmati")
    cauli = sum(comp.grams for p in c.plates for comp in p.components if comp.ingredient.key == "cauliflower_rice")
    assert rice > 0 and cauli > 0  # Dale has rice, Jade has the cauliflower swap
    assert items["brown_basmati"].grams == pytest.approx(rice)
    assert items["cauliflower_rice"].grams == pytest.approx(cauli)


def test_chosen_swap_changes_the_list(catalogue, recipes, targets):
    everyone_cauli = {(p, m): {"carb": FlexChoice(option="cauliflower_rice")}
                      for p in ("dale", "jade") for m in ("dinner", "lunch")}
    c = cook(recipes, catalogue, targets, "chicken-tikka-traybake", choices=everyone_cauli)
    keys = by_key(build_list([c], catalogue, set()))
    assert "brown_basmati" not in keys and keys["cauliflower_rice"].grams == pytest.approx(600)


def test_duplicates_merge_across_recipes(catalogue, recipes, targets):
    cooks = [cook(recipes, catalogue, targets, s) for s in ("turkey-chilli", "turkey-lentil-bolognese")]
    items = by_key(build_list(cooks, catalogue, set()))
    assert items["turkey_mince"].grams == pytest.approx(750 + 600)
    assert items["turkey_mince"].recipes == [cooks[0].recipe.title, cooks[1].recipe.title]
    assert items["chopped_tomatoes"].buy_text == "4 x 400 g tin"


def test_pantry_staples_are_flagged(catalogue, recipes, targets):
    c = cook(recipes, catalogue, targets, "turkey-chilli")
    items = by_key(build_list([c], catalogue, {"olive_oil", "ground_cumin"}))
    assert items["olive_oil"].staple and items["ground_cumin"].staple and not items["turkey_mince"].staple


def test_grouped_by_aisle_in_shop_order(catalogue, recipes, targets):
    c = cook(recipes, catalogue, targets, "chicken-tikka-traybake")
    aisles = [a for a, _ in group_by_aisle(build_list([c], catalogue, set()))]
    assert aisles[0] == "Fruit & veg"
    assert aisles.index("Meat & poultry") < aisles.index("Dairy & eggs") < aisles.index("Herbs & spices")


def test_plain_text_export(catalogue, recipes, targets):
    c = cook(recipes, catalogue, targets, "turkey-chilli")
    items = build_list([c], catalogue, {"olive_oil"})
    text = as_text(items, "Shopping", ticked={"turkey_mince"})
    assert text.startswith("Shopping\n\nFRUIT & VEG\n")
    assert "[x] Turkey breast mince (2% fat): 2 x 500 g pack" in text
    assert "[ ] Chopped tomatoes: 2 x 400 g tin" in text
    assert text.rstrip().endswith("CHECK THE CUPBOARD: Olive oil")


# --- Cooking quantities and plating guide -----------------------------------------------

def test_cook_base_keeps_friendly_amounts_and_scales(catalogue, recipes):
    chilli = next(r for r in recipes if r.slug == "turkey-chilli")
    full = cook_base(chilli, catalogue, 4)
    assert full[0].text == "1 tbsp olive oil"
    assert full[1].text == "1 x onions" and full[1].note == "chopped"
    half = cook_base(chilli, catalogue, 2)
    assert half[4].grams == pytest.approx(375) and "scaled from" in half[4].text


def test_cook_flex_combines_and_shares(catalogue, recipes, targets):
    c = cook(recipes, catalogue, targets, "chicken-tikka-traybake")
    lines = {l.ingredient.key: l for l in cook_flex(c.plates)}
    rice = lines["brown_basmati"]
    assert {(s.person, s.meal) for s in rice.shares} == {("dale", "dinner"), ("dale", "lunch")}
    assert sum(s.percent for s in rice.shares) in (99, 100, 101)
    assert rice.cooked_grams == round(rice.grams * 2.6 / 5) * 5
    assert "dry brown basmati rice" in rice.text and "cooked" in rice.text


def test_pot_shares(catalogue, recipes, targets):
    c = cook(recipes, catalogue, targets, "turkey-chilli")
    assert pot_shares(c.plates) == {(p, m): 25 for p in ("dale", "jade") for m in ("dinner", "lunch")}
    c2 = cook(recipes, catalogue, targets, "steak-chimichurri", portions=2)
    assert pot_shares(c2.plates) == {("dale", "dinner"): 50, ("jade", "dinner"): 50}


def test_amount_text(catalogue):
    assert amount_text(catalogue["wholemeal_tortilla"], 128) == "2 x wholemeal tortilla wraps"
    assert amount_text(catalogue["brown_basmati"], 130) == "130 g dry brown basmati rice"
    assert amount_text(catalogue["spinach"], 240) == "240 g baby spinach"
