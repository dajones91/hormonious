"""Nutrition-rule validation, checked on each person's plated portion."""

from core.nutrition import Nutrition
from core.portions import MealTarget, Plate, base_shares, plan_plates
from core.rules import Issue, RuleSettings, check_plate, check_structure, passes, validate
from core.schema import Recipe

JADE = MealTarget(500, 35, 45, 45, 8)
DALE = MealTarget(750, 45, 75, None, 8)
S = RuleSettings()


def plate(person="jade", **n) -> Plate:
    return Plate(person, "dinner", 0.5, Nutrition(**n), base_added_sugar=0)


def messages(issues):
    return [i.message.split(" ")[0] for i in issues if i.level == "fail"]


def test_good_plate_passes():
    assert check_plate(plate(kcal=480, protein=40, carbs=30, fibre=9), JADE, S) == []


def test_low_protein_fails():
    assert messages(check_plate(plate(kcal=480, protein=30, carbs=30, fibre=9), JADE, S)) == ["protein"]


def test_low_fibre_fails():
    assert messages(check_plate(plate(kcal=480, protein=40, carbs=30, fibre=6), JADE, S)) == ["fibre"]


def test_carbs_over_jades_cap_fails_but_dale_has_no_cap():
    assert messages(check_plate(plate(kcal=480, protein=40, carbs=50, fibre=9), JADE, S)) == ["carbs"]
    assert check_plate(plate("dale", kcal=740, protein=50, carbs=90, fibre=9), DALE, S) == []


def test_rounding_matches_what_we_show():
    # 7.6 g fibre is shown as 8 g, so it meets an 8 g target
    assert check_plate(plate(kcal=480, protein=34.6, carbs=45.4, fibre=7.6), JADE, S) == []


def test_added_sugar_limit():
    p = Plate("jade", "dinner", 0.5, Nutrition(kcal=480, protein=40, carbs=30, fibre=9), base_added_sugar=7)
    assert messages(check_plate(p, JADE, S)) == ["added"]


def test_big_plate_is_a_warning_not_a_fail():
    issues = check_plate(plate(kcal=650, protein=40, carbs=30, fibre=9), JADE, S)
    assert [i.level for i in issues] == ["warn"]


def recipe_dict(**over):
    data = dict(slug="r", title="R", tier="weeknight", cuisine="x", active_min=10, total_min=30,
                tags=["lunchbox-friendly"], steps=["cook"],
                shared=[{"ingredient": "chicken_breast", "grams": 700}, {"ingredient": "spinach", "grams": 400},
                        {"ingredient": "olive_oil", "grams": 14}])
    data.update(over)
    return data


def test_structure_rules(catalogue):
    assert check_structure(Recipe(**recipe_dict()), catalogue, S) == []
    no_fat = recipe_dict(shared=[{"ingredient": "chicken_breast", "grams": 700},
                                 {"ingredient": "spinach", "grams": 400}])
    assert [i.message for i in check_structure(Recipe(**no_fat), catalogue, S)] == ["no a healthy fat in the shared base"]
    slow = check_structure(Recipe(**recipe_dict(total_min=50)), catalogue, S)
    assert slow[0].message == "takes 50 min, limit 45"
    assert check_structure(Recipe(**recipe_dict(tier="weekend", total_min=80, tags=[])), catalogue, S) == []
    no_box = check_structure(Recipe(**recipe_dict(tags=[])), catalogue, S)
    assert "lunchbox-friendly" in no_box[0].message


def test_refined_carb_needs_a_low_gi_swap(catalogue):
    white_only = {"component": "carb", "options": [
        {"ingredient": "white_basmati", "standard_grams": 60, "max_grams": 100, "default": True}]}
    with_swap = {"component": "carb", "options": [
        {"ingredient": "white_basmati", "standard_grams": 60, "max_grams": 100, "default": True},
        {"ingredient": "cauliflower_rice", "standard_grams": 150, "max_grams": 300}]}
    assert not passes(check_structure(Recipe(**recipe_dict(flexible=[white_only])), catalogue, S))
    assert passes(check_structure(Recipe(**recipe_dict(flexible=[with_swap])), catalogue, S))


def test_weekend_nutrition_is_loose(catalogue):
    targets = {"dale": {"dinner": DALE, "lunch": DALE}, "jade": {"dinner": JADE, "lunch": JADE}}
    low_fibre = recipe_dict(shared=[{"ingredient": "beef_sirloin", "grams": 800},
                                    {"ingredient": "cherry_tomatoes", "grams": 100},
                                    {"ingredient": "olive_oil", "grams": 14}],
                            tags=[])
    for tier, expect in (("weeknight", False), ("weekend", True)):
        r = Recipe(**{**low_fibre, "tier": tier, "tags": ["lunchbox-friendly"]})
        plates = plan_plates(r, catalogue, targets, base_shares(r, "even", {}, targets))
        issues = validate(r, catalogue, plates, targets, S)
        assert passes(issues) is expect
        assert any("fibre" in i.message for i in issues)


def test_issue_text():
    assert str(Issue("fail", "fibre 6 g", "jade", "lunch")) == "Jade lunch: fibre 6 g"


def test_every_seed_recipe_passes_with_default_targets(catalogue, recipes):
    from core.loaders import load_household
    h = load_household()
    targets = {p: {m: MealTarget(**t) for m, t in meals.items()} for p, meals in h["targets"].items()}
    failing = {}
    for r in recipes:
        plates = plan_plates(r, catalogue, targets, base_shares(r, "even", {}, targets))
        issues = validate(r, catalogue, plates, targets, S)
        if not passes(issues):
            failing[r.slug] = [str(i) for i in issues if i.level == "fail"]
    assert failing == {}
