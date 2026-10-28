"""Smoke tests for the web pages, using a throwaway database file."""

from datetime import date

import pytest

from app import create_app
from db.repo import reset_and_seed


@pytest.fixture
def client(tmp_path):
    app = create_app(f"sqlite:///{tmp_path / 'test.db'}", today=date(2026, 10, 26))
    with app.app_context():
        with app.config["SESSION_FACTORY"]() as session:
            reset_and_seed(session)
    return app.test_client()


def test_pages_load(client):
    assert client.get("/").status_code == 302
    for path in ("/week", "/week/2026-10-31", "/recipes", "/profiles", "/recipe/turkey-chilli"):
        page = client.get(path)
        assert page.status_code == 200, path
        assert b"isn't medical advice" in page.data


def test_week_must_start_on_saturday(client):
    assert client.get("/week/2026-11-02").status_code == 404


def test_week_shows_menu_and_plan(client):
    page = client.get("/week").get_data(as_text=True)
    assert "Week from Sat 31 Oct" in page
    assert "lunch Mon" in page  # Sunday's 4 portions cover Monday lunch
    assert page.count('name="slot-') == 6  # Friday has no plan by default


def test_save_plan(client):
    page = client.get("/week/2026-10-31").get_data(as_text=True)
    form = {"slot-2026-11-02": "turkey-chilli", "slot-2026-11-03": "no-cook", "slot-2026-11-04": "tuscan-chicken"}
    saved = client.post("/week/2026-10-31", data=form, follow_redirects=True).get_data(as_text=True)
    assert "Plan saved." in saved
    assert '<option value="turkey-chilli" selected>' in saved
    assert '<option value="no-cook" selected>' in saved
    assert "2 cooking nights" in saved


def test_off_menu_recipe_stays_selected(client):
    page = client.get("/week/2026-10-31").get_data(as_text=True)
    menu = page.split("This week's menu")[1]
    off_menu = next(slug for slug in ("lamb-rogan-josh", "steak-chimichurri", "chicken-chickpea-tagine",
                                      "crispy-cod-chips-peas") if f"/recipe/{slug}" not in menu)
    client.post("/week/2026-10-31", data={"slot-2026-11-01": off_menu})
    page = client.get("/week/2026-10-31").get_data(as_text=True)
    assert f'<option value="{off_menu}" selected>' in page


def test_same_recipe_twice_is_rejected(client):
    form = {"slot-2026-11-02": "turkey-chilli", "slot-2026-11-03": "turkey-chilli"}
    page = client.post("/week/2026-10-31", data=form, follow_redirects=True).get_data(as_text=True)
    assert "only go on one night" in page


def test_last_weeks_recipes_left_off_next_menu(client):
    client.get("/week/2026-10-31")
    client.post("/week/2026-10-31", data={"slot-2026-11-02": "turkey-chilli"})
    next_week = client.get("/week/2026-11-07").get_data(as_text=True)
    menu = next_week.split("This week's menu")[1]
    assert "Smoky turkey and two-bean chilli" not in menu


def test_recipe_page_shows_per_person_plates(client):
    page = client.get("/recipe/chicken-tikka-traybake").get_data(as_text=True)
    for label in ("Dale dinner", "Jade dinner", "Dale lunch", "Jade lunch", "cauliflower rice"):
        assert label in page


def test_profiles_save_and_change_portions(client):
    form = {}
    for person, kcal in (("dale", 750), ("jade", 400)):
        for meal in ("dinner", "lunch"):
            form.update({f"{person}-{meal}-kcal": kcal, f"{person}-{meal}-protein_min": 35,
                         f"{person}-{meal}-carbs_target": 45, f"{person}-{meal}-carbs_max": "",
                         f"{person}-{meal}-fibre_min": 8})
    form.update({"split_mode": "protein", "fixed_dale": 55})
    page = client.post("/profiles", data=form, follow_redirects=True).get_data(as_text=True)
    assert "Profiles saved" in page
    assert 'value="400"' in page and 'value="protein" checked' in page


def plan_two_nights(client):
    client.get("/week/2026-10-31")
    client.post("/week/2026-10-31", data={"slot-2026-11-02": "chicken-tikka-traybake",
                                          "slot-2026-10-31": "steak-chimichurri"})
    page = client.get("/week/2026-10-31").get_data(as_text=True)
    return [int(part.split('"')[0]) for part in page.split('href="/cook/')[1:]]


def test_cook_card_shows_plating_guide(client):
    monday = plan_two_nights(client)[1]
    page = client.get(f"/cook/{monday}").get_data(as_text=True)
    assert "Plating guide" in page and "Lunch box (next day)" in page
    assert "25% of the pot" in page
    assert "dry brown basmati rice" in page and "cooked)" in page
    assert "Keep screen on" in page


def test_two_portion_night_has_no_lunch(client):
    saturday = plan_two_nights(client)[0]
    page = client.get(f"/cook/{saturday}").get_data(as_text=True)
    assert "Lunch box" not in page and "50% of the pot" in page
    assert "400 g beef sirloin steak (scaled from 4 steaks)" in page


def test_portion_change_updates_card_and_shopping(client):
    monday = plan_two_nights(client)[1]
    before = client.get("/shopping/2026-10-31").get_data(as_text=True)
    assert "Brown basmati rice" in before
    form = {f"{p}-{m}-carb-option": "cauliflower_rice" for p in ("dale", "jade") for m in ("dinner", "lunch")}
    page = client.post(f"/cook/{monday}", data=form, follow_redirects=True).get_data(as_text=True)
    assert "Portions updated" in page and "your choice" in page
    after = client.get("/shopping/2026-10-31").get_data(as_text=True)
    assert "Brown basmati rice" not in after
    assert "need 600 g" in after  # 4 x 150 g cauliflower rice


def test_portion_grams_override_and_bad_input(client):
    monday = plan_two_nights(client)[1]
    page = client.post(f"/cook/{monday}", data={"jade-dinner-carb-grams": "40"}, follow_redirects=True)
    assert "40 g dry brown basmati rice" in page.get_data(as_text=True)
    bad = client.post(f"/cook/{monday}", data={"jade-dinner-carb-grams": "lots"}, follow_redirects=True)
    assert "isn&#39;t a number" in bad.get_data(as_text=True)
    assert client.post(f"/cook/{monday}", data={"jade-dinner-carb-option": "chocolate"}).status_code == 400


def test_changing_the_recipe_clears_portion_changes(client):
    monday = plan_two_nights(client)[1]
    client.post(f"/cook/{monday}", data={"dale-dinner-carb-grams": "100"})
    client.post("/week/2026-10-31", data={"slot-2026-11-02": "turkey-chilli", "slot-2026-10-31": "steak-chimichurri"})
    page = client.get(f"/cook/{monday}").get_data(as_text=True)
    assert "your choice" not in page


def test_shopping_list_grouped_and_ticking(client):
    plan_two_nights(client)
    page = client.get("/shopping/2026-10-31").get_data(as_text=True)
    assert page.index("Fruit &amp; veg") < page.index("Meat &amp; poultry")
    assert "Pantry staples we should already have" in page
    tick = client.post("/shopping/2026-10-31/tick/chicken_breast", headers={"HX-Request": "true"})
    assert tick.status_code == 200 and 'class="shop-item done"' in tick.get_data(as_text=True)
    text = client.get("/shopping/2026-10-31.txt").get_data(as_text=True)
    assert "[x] Chicken breast fillets" in text and "CHECK THE CUPBOARD" in text
    client.post("/shopping/2026-10-31/tick/chicken_breast")  # untick without HTMX
    assert "[ ] Chicken breast fillets" in client.get("/shopping/2026-10-31.txt").get_data(as_text=True)
    assert client.post("/shopping/2026-10-31/tick/not_a_thing").status_code == 404


def test_pantry_toggle(client):
    plan_two_nights(client)
    client.post("/shopping/2026-10-31/pantry/garlic")
    text = client.get("/shopping/2026-10-31.txt").get_data(as_text=True)
    assert "] Garlic" not in text and "Garlic" in text.split("CHECK THE CUPBOARD")[1]
    client.post("/shopping/2026-10-31/pantry/garlic")
    assert "[ ] Garlic" in client.get("/shopping/2026-10-31.txt").get_data(as_text=True)


def test_empty_shopping_list(client):
    assert client.get("/shopping").status_code == 302
    assert "Nothing planned yet" in client.get("/shopping/2026-10-31").get_data(as_text=True)


def test_bad_profile_input_is_not_saved(client):
    page = client.post("/profiles", data={"dale-dinner-kcal": "lots"}, follow_redirects=True).get_data(as_text=True)
    assert "Not saved" in page
