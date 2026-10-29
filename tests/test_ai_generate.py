"""AI recipe generation, tested with a fake AI (no API key needed, nothing is spent)."""

from datetime import date

import pytest

from ai.generate import AiError, call_claude, check_answer, generate_recipe, system_prompt
from ai.schema import AiAnswer, AiNewIngredient
from app import create_app
from db.planner import generate_and_save
from db.repo import get_catalogue, get_recipe, reset_and_seed


def answer_from(base, title, **changes) -> AiAnswer:
    """Build an AI-style answer from one of our seed recipes, with a new title and optional changes."""
    data = base.model_dump()
    r = {k: data[k] for k in ("tier", "cuisine", "spice", "active_min", "total_min", "tags", "steps")}
    r.update(title=title, reheat_note=data["reheat_note"] or "Microwave until piping hot.",
             shared=[{"ingredient": i["ingredient"], "grams": i["grams"], "display": i["display"], "note": i["note"]}
                     for i in data["shared"]],
             flexible=[{"component": c["component"], "cook_note": c["cook_note"], "options": c["options"]}
                       for c in data["flexible"]])
    r.update(changes.pop("recipe", {}))
    return AiAnswer(recipe=r, new_ingredients=changes.pop("new_ingredients", []))


class FakeAI:
    """Returns prepared answers in order, and remembers what it was asked."""

    def __init__(self, *answers):
        self.answers = list(answers)
        self.prompts = []

    def __call__(self, system, user):
        self.prompts.append(user)
        return self.answers.pop(0), {"input": 10_000, "output": 3_000}


PAK_CHOI = AiNewIngredient(key="pak_choi", name="Pak choi", aisle="Fruit & veg", state="raw", kcal=13, protein=1.5,
                           carbs=1.2, sugars=1.2, fibre=1.0, fat=0.2, cooked_yield=1, gi="low", flags=["vegetable"],
                           pack_unit="g", pack_size=200, pack_label="pack", unit_g=None)


@pytest.fixture
def session(tmp_path):
    app = create_app(f"sqlite:///{tmp_path / 'ai.db'}", today=date(2026, 10, 26))
    with app.app_context(), app.config["SESSION_FACTORY"]() as s:
        reset_and_seed(s)
        yield s


@pytest.fixture
def satay(recipes):
    return next(r for r in recipes if r.slug == "chicken-satay-stir-fry")


def test_good_recipe_saved_first_time(session, satay):
    fake = FakeAI(answer_from(satay, "Sesame chicken and greens noodle bowl"))
    result = generate_and_save(session, "weeknight", "something with noodles", call=fake)
    assert result.ok and result.attempts == 1
    saved = get_recipe(session, "sesame-chicken-and-greens-noodle-bowl")
    assert saved.source == "ai" and saved.servings == 4
    assert "something with noodles" in fake.prompts[0] and "WEEKNIGHT" in fake.prompts[0]
    assert result.cost_usd == pytest.approx((10_000 * 4 + 3_000 * 20) / 1e6)


def test_excluded_ingredient_rejected_then_fixed(session, satay, recipes):
    salmon = answer_from(satay, "Salmon satay noodles", recipe={
        "shared": [*answer_from(satay, "x").recipe.model_dump()["shared"],
                   {"ingredient": "salmon_fillet", "grams": 400, "display": None, "note": None}]})
    fake = FakeAI(salmon, answer_from(satay, "Chicken satay noodles without the fish"))
    result = generate_and_save(session, "weeknight", "", call=fake)
    assert result.ok and result.attempts == 2
    assert any("salmon" in p.lower() for p in result.problems[0])
    assert "rejected by our checks" in fake.prompts[1] and "Salmon" in fake.prompts[1]


def test_nothing_saved_when_every_attempt_fails(session, satay):
    too_slow = answer_from(satay, "Very slow satay", recipe={"total_min": 80, "active_min": 30})
    fake = FakeAI(too_slow, too_slow, too_slow)
    result = generate_and_save(session, "weeknight", "", call=fake)
    assert not result.ok and result.attempts == 3 and len(result.problems) == 3
    assert any("takes 80 min" in p for p in result.problems[0])
    assert get_recipe(session, "very-slow-satay") is None


def test_unknown_ingredient_and_duplicate_title(session, satay):
    cat = get_catalogue(session)
    bad = answer_from(satay, "Chicken satay stir-fry with edamame", recipe={
        "shared": [{"ingredient": "dragon_eggs", "grams": 100, "display": None, "note": None}]})
    recipe, _, problems = check_answer(bad, cat, lambda r, c: [], {"chicken satay stir-fry with edamame"}, set())
    assert recipe is None
    assert any("dragon_eggs" in p for p in problems) and any("already have" in p for p in problems)


def test_new_ingredient_saved_as_unverified_estimate(session, satay):
    shared = answer_from(satay, "x").recipe.model_dump()["shared"]
    shared.append({"ingredient": "pak_choi", "grams": 300, "display": "2 heads", "note": "quartered"})
    fake = FakeAI(answer_from(satay, "Satay chicken with pak choi", recipe={"shared": shared},
                              new_ingredients=[PAK_CHOI]))
    result = generate_and_save(session, "weeknight", "", call=fake)
    assert result.ok and [i.key for i in result.new_ingredients] == ["pak_choi"]
    pak = get_catalogue(session)["pak_choi"]
    assert pak.source == "ai-estimate" and not pak.verified and pak.packs == [200]


def test_new_ingredient_checked_for_exclusions(session, satay):
    shiitake = PAK_CHOI.model_copy(update={"key": "shiitake", "name": "Shiitake mushrooms"})
    shared = answer_from(satay, "x").recipe.model_dump()["shared"]
    shared.append({"ingredient": "shiitake", "grams": 150, "display": None, "note": None})
    bad = answer_from(satay, "Shiitake satay", recipe={"shared": shared}, new_ingredients=[shiitake])
    fake = FakeAI(bad, bad, bad)
    result = generate_and_save(session, "weeknight", "", call=fake)
    assert not result.ok and any("mushroom" in p for p in result.problems[0])


def test_slug_made_unique(session, satay):
    cat = get_catalogue(session)
    recipe, _, problems = check_answer(answer_from(satay, "Turkey chilli"), cat, lambda r, c: [], set(), {"turkey-chilli"})
    assert problems == [] and recipe.slug == "turkey-chilli-2"


def test_system_prompt_has_our_rules_but_hides_excluded_ingredients(session):
    from db.planner import load_context, targets_text
    from db.repo import get_exclusion_notes
    ctx = load_context(session)
    text = system_prompt(ctx.catalogue, targets_text(ctx.targets, True), "\n".join(get_exclusion_notes(session)),
                         ["Turkey chilli"])
    assert "Jade: No fish or shellfish" in text and "no meat substitutes" in text.lower()
    assert "Jade dinner: about 500 kcal" in text and "same as their dinner" in text
    assert "chicken_breast |" in text and "salmon_fillet" not in text and "chestnut_mushrooms" not in text
    assert "- Turkey chilli" in text and "medical" in text
    assert "Plate using the plating guide" in text  # the app, not the recipe, sets each share


def test_missing_api_key_gives_a_clear_message(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(AiError, match="ANTHROPIC_API_KEY"):
        call_claude("system", "user")


# --- Web pages -------------------------------------------------------------------------------

@pytest.fixture
def web(tmp_path):
    app = create_app(f"sqlite:///{tmp_path / 'aiweb.db'}", today=date(2026, 10, 26))
    with app.app_context(), app.config["SESSION_FACTORY"]() as s:
        reset_and_seed(s)
    return app


def test_generate_button_saves_and_opens_the_recipe(web, satay):
    web.config["AI_CALL"] = FakeAI(answer_from(satay, "Peanut chicken noodle bowl"))
    c = web.test_client()
    resp = c.post("/recipes/generate", data={"tier": "weeknight", "idea": "peanut"}, follow_redirects=True)
    page = resp.get_data(as_text=True)
    assert "New recipe added" in page and "AI recipe" in page and "Peanut chicken noodle bowl" in page
    assert "Remove from library" in page
    c.post("/recipe/peanut-chicken-noodle-bowl/remove")
    assert "Peanut chicken noodle bowl" not in c.get("/recipes").get_data(as_text=True)


def test_generate_failure_is_explained(web, satay):
    slow = answer_from(satay, "Slow one", recipe={"total_min": 80})
    web.config["AI_CALL"] = FakeAI(slow, slow, slow)
    page = web.test_client().post("/recipes/generate", data={"tier": "weeknight"}, follow_redirects=True)
    assert "none of the 3 attempts passed" in page.get_data(as_text=True)


def test_generate_api_error_is_shown(web):
    def broken(system, user):
        raise AiError("No Anthropic API key found. Add ANTHROPIC_API_KEY to your .env file.")
    web.config["AI_CALL"] = broken
    page = web.test_client().post("/recipes/generate", data={"tier": "weekend"}, follow_redirects=True)
    assert "No Anthropic API key found" in page.get_data(as_text=True)


def test_seed_recipes_cannot_be_removed(web):
    assert web.test_client().post("/recipe/turkey-chilli/remove").status_code == 404
