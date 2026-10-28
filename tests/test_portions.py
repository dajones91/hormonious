"""Per-person portions: base split, flexible sizing, swaps and totals."""

import pytest

from core.nutrition import Nutrition, items_total
from core.portions import (FlexChoice, MealTarget, base_shares, build_plate, meals_for_portions, plan_plates,
                           size_carb)
from core.schema import FlexOption, Ingredient, Recipe

T = {
    "dale": {"dinner": MealTarget(750, 45, 75, None, 8), "lunch": MealTarget(650, 40, 60, None, 8)},
    "jade": {"dinner": MealTarget(500, 35, 45, 45, 8), "lunch": MealTarget(450, 35, 40, 40, 8)},
}


def ing(key, kcal, protein=0.0, carbs=0.0, fibre=0.0, fat=0.0, flags=(), state="raw", **kw):
    return Ingredient(key=key, name=key.replace("_", " ").title(), aisle="x", state=state, kcal=kcal,
                      protein=protein, carbs=carbs, sugars=0, fibre=fibre, fat=fat, flags=set(flags), **kw)


CAT = {
    "chicken": ing("chicken", 100, protein=25, flags={"protein"}),
    "veg": ing("veg", 25, protein=2, carbs=4, fibre=3, flags={"vegetable"}),
    "oil": ing("oil", 900, fat=100, flags={"healthy_fat"}),
    "rice": ing("rice", 350, protein=8, carbs=75, fibre=3, state="dry", cooked_yield=2.6),
    "cauli": ing("cauli", 25, protein=2, carbs=2.5, fibre=2, flags={"vegetable"}),
    "cheese": ing("cheese", 400, protein=25, fat=33),
    "wrap": ing("wrap", 260, protein=9, carbs=42, fibre=6, pack_unit="each", unit_g=64),
}


def recipe(flexible=(), base_split=None, servings=4):
    return Recipe(
        slug="test", title="Test", tier="weeknight", cuisine="x", active_min=10, total_min=30,
        tags=["lunchbox-friendly"], steps=["cook"], servings=servings, base_split=base_split,
        shared=[{"ingredient": "chicken", "grams": 800}, {"ingredient": "veg", "grams": 800},
                {"ingredient": "oil", "grams": 20}],
        flexible=list(flexible),
    )


CARB = {"component": "carb", "options": [
    {"ingredient": "rice", "standard_grams": 60, "min_grams": 0, "max_grams": 110, "default": True},
    {"ingredient": "cauli", "standard_grams": 150, "min_grams": 0, "max_grams": 300},
]}


# --- Splitting the shared base -------------------------------------------------

def test_even_split_by_default():
    assert base_shares(recipe(), "even", {}, T) == {"dale": 0.5, "jade": 0.5}


def test_split_by_protein_target():
    shares = base_shares(recipe(), "protein", {}, T)
    assert shares["dale"] == pytest.approx(45 / 80) and shares["jade"] == pytest.approx(35 / 80)


def test_fixed_split_and_recipe_override_wins():
    assert base_shares(recipe(), "fixed", {"dale": 0.55, "jade": 0.45}, T) == {"dale": 0.55, "jade": 0.45}
    assert base_shares(recipe(base_split={"dale": 0.6, "jade": 0.4}), "even", {}, T) == {"dale": 0.6, "jade": 0.4}


def test_base_split_between_people_and_meals():
    # 800 g chicken (200 g protein) over 4 portions: each meal gets half; Jade gets 45% of a meal
    plate = build_plate(recipe(), CAT, "jade", "dinner", 0.45, T["jade"]["dinner"])
    assert plate.base.protein == pytest.approx(200 / 2 * 0.45 + 16 / 2 * 0.45)


def test_all_four_plates_add_up_to_the_whole_base():
    r = recipe()
    plates = plan_plates(r, CAT, T, {"dale": 0.55, "jade": 0.45})
    assert len(plates) == 4
    total_kcal = sum(p.base.kcal for p in plates)
    assert total_kcal == pytest.approx(items_total(r.shared, CAT).kcal)


def test_two_portions_is_dinner_only():
    assert meals_for_portions(2) == ("dinner",)
    assert meals_for_portions(4) == ("dinner", "lunch")


# --- Sizing the flexible carb ----------------------------------------------------

def test_carb_fills_remaining_kcal():
    opt = FlexOption(ingredient="rice", standard_grams=60, max_grams=200)
    # 750 target, 400 used -> 350 kcal left -> 100 g rice (75 g carbs, fits Dale's 75 target exactly)
    assert size_carb(opt, CAT["rice"], T["dale"]["dinner"], Nutrition(kcal=400)) == 100


def test_carb_limited_by_carb_cap_not_kcal():
    opt = FlexOption(ingredient="rice", standard_grams=60, max_grams=200)
    # Jade: 300 kcal left would allow 85 g, but only 15 g carbs left (45 cap - 30 used) -> 20 g
    assert size_carb(opt, CAT["rice"], T["jade"]["dinner"], Nutrition(kcal=200, carbs=30)) == 20


def test_carb_clamped_to_option_range_and_rounded_to_5():
    opt = FlexOption(ingredient="rice", standard_grams=60, min_grams=0, max_grams=110)
    no_carb_limit = MealTarget(750, 45, 999, None, 8)
    assert size_carb(opt, CAT["rice"], no_carb_limit, Nutrition()) == 110  # would be 214 g, max is 110
    assert size_carb(opt, CAT["rice"], MealTarget(486, 0, 999, None, 0), Nutrition(kcal=400)) == 25  # 24.6 g


def test_token_amount_becomes_none():
    opt = FlexOption(ingredient="rice", standard_grams=60, max_grams=110)
    assert size_carb(opt, CAT["rice"], T["jade"]["dinner"], Nutrition(kcal=460)) == 0  # 11 g < 60/5


def test_wraps_are_whole_items():
    opt = FlexOption(ingredient="wrap", standard_grams=64, max_grams=128)
    grams = size_carb(opt, CAT["wrap"], T["dale"]["dinner"], Nutrition(kcal=450, carbs=20))
    assert grams in (64, 128) and grams == 128  # 300 kcal left -> 115 g -> 2 wraps


def test_jade_gets_vegetable_swap_when_rice_would_be_tiny():
    r = recipe([CARB])
    # base is ~295 kcal, so a 350 kcal target leaves room for only ~16 g rice (under half of 60 g)
    plate = build_plate(r, CAT, "jade", "dinner", 0.5, MealTarget(350, 35, 45, 45, 8))
    carb = plate.components[0]
    assert carb.ingredient.key == "cauli" and carb.sized_by == "swap" and carb.grams == 150


def test_dale_gets_rice_sized_to_his_target():
    r = recipe([CARB])
    plate = build_plate(r, CAT, "dale", "dinner", 0.5, T["dale"]["dinner"])
    carb = plate.components[0]
    assert carb.ingredient.key == "rice" and carb.sized_by == "target"
    # carb-limited here: 8 g carbs in the base + 90 g rice (67.5 g) = ~75 g, Dale's carb target
    assert plate.total.carbs == pytest.approx(75, abs=3)
    assert plate.total.kcal < 750


def test_dry_and_cooked_weights():
    r = recipe([CARB])
    carb = build_plate(r, CAT, "dale", "dinner", 0.5, T["dale"]["dinner"]).components[0]
    assert carb.weight_label == "dry"
    assert carb.cooked_grams == round(carb.grams * 2.6 / 5) * 5


def test_person_can_choose_a_swap_or_set_grams():
    r = recipe([CARB])
    swap = build_plate(r, CAT, "dale", "dinner", 0.5, T["dale"]["dinner"], {"carb": FlexChoice(option="cauli")})
    assert swap.components[0].ingredient.key == "cauli"
    fixed = build_plate(r, CAT, "jade", "dinner", 0.5, T["jade"]["dinner"], {"carb": FlexChoice(grams=33)})
    assert fixed.components[0].grams == 35 and fixed.components[0].sized_by == "you"


def test_toppings_use_standard_size_and_count_before_the_carb():
    topping = {"component": "topping", "options": [
        {"ingredient": "cheese", "standard_grams": 20, "max_grams": 40, "default": True}]}
    r = recipe([CARB, topping])
    kcal_limited = MealTarget(650, 45, 999, None, 8)
    with_cheese = build_plate(r, CAT, "dale", "dinner", 0.5, kcal_limited)
    without = build_plate(recipe([CARB]), CAT, "dale", "dinner", 0.5, kcal_limited)
    assert with_cheese.components[1].grams == 20
    assert with_cheese.components[0].grams < without.components[0].grams  # less rice to make room


def test_recipe_without_flexible_parts_is_a_standard_portion():
    plate = build_plate(recipe(), CAT, "dale", "dinner", 0.5, T["dale"]["dinner"])
    assert plate.components == [] and plate.total == plate.base


def test_unknown_swap_is_rejected():
    with pytest.raises(ValueError):
        build_plate(recipe([CARB]), CAT, "dale", "dinner", 0.5, T["dale"]["dinner"], {"carb": FlexChoice("pasta")})
