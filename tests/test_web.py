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
    page = client.get("/week/2026-10-31").get_data(as_text=True)
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
    menu = page.split("<h2>The menu</h2>")[1]
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
    menu = next_week.split("<h2>The menu</h2>")[1]
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
    """Plan Saturday and Monday; return their card ids [saturday, monday] via the open-card button."""
    client.get("/week/2026-10-31")
    plan = {"slot-2026-11-02": "chicken-tikka-traybake", "slot-2026-10-31": "steak-chimichurri"}
    ids = []
    for day in ("2026-10-31", "2026-11-02"):
        resp = client.post("/week/2026-10-31", data={**plan, "open": day})
        ids.append(int(resp.headers["Location"].rsplit("/", 1)[1]))
    return ids


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
    form = {f"{p}-both-carb-option": "cauliflower_rice" for p in ("dale", "jade")}
    page = client.post(f"/cook/{monday}", data=form, follow_redirects=True).get_data(as_text=True)
    assert "Portions updated" in page and "your choice" in page
    after = client.get("/shopping/2026-10-31").get_data(as_text=True)
    assert "Brown basmati rice" not in after
    assert "need 600 g" in after  # 4 x 150 g cauliflower rice


def test_portion_grams_override_and_bad_input(client):
    monday = plan_two_nights(client)[1]
    page = client.post(f"/cook/{monday}", data={"jade-both-carb-grams": "40"}, follow_redirects=True)
    assert "40 g dry brown basmati rice" in page.get_data(as_text=True)
    bad = client.post(f"/cook/{monday}", data={"jade-both-carb-grams": "lots"}, follow_redirects=True)
    assert "isn&#39;t a number" in bad.get_data(as_text=True)
    assert client.post(f"/cook/{monday}", data={"jade-both-carb-option": "chocolate"}).status_code == 400


def test_changing_the_recipe_clears_portion_changes(client):
    monday = plan_two_nights(client)[1]
    client.post(f"/cook/{monday}", data={"dale-both-carb-grams": "100"})
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


def test_open_recipe_card_saves_dropdown_change_first(client):
    monday = plan_two_nights(client)[1]
    # change Monday in the dropdown, then press that night's "Open recipe card" without saving
    form = {"slot-2026-11-02": "turkey-chilli", "slot-2026-10-31": "steak-chimichurri", "open": "2026-11-02"}
    resp = client.post("/week/2026-10-31", data=form)
    assert resp.headers["Location"].endswith(f"/cook/{monday}")
    assert "Smoky turkey and two-bean chilli" in client.get(f"/cook/{monday}").get_data(as_text=True)


def test_open_on_a_night_with_no_recipe(client):
    page = client.post("/week/2026-10-31", data={"open": "2026-11-03"}, follow_redirects=True)
    assert "no recipe on that night" in page.get_data(as_text=True)


def test_lunch_matches_dinner_and_one_choice_covers_both(client):
    monday = plan_two_nights(client)[1]
    page = client.get(f"/cook/{monday}").get_data(as_text=True)
    assert "dinner + lunch" in page and "jade-dinner-carb-option" not in page
    client.post(f"/cook/{monday}", data={"dale-both-carb-grams": "60"})
    page = client.get(f"/cook/{monday}").get_data(as_text=True)
    assert page.count("60 g dry brown basmati rice") == 2  # dinner and lunch box



def test_week_tab_opens_on_the_current_week(client):
    page = client.get("/week").get_data(as_text=True)  # today is Monday 26 Oct
    assert "Week from Sat 24 Oct" in page and ">This week<" in page


def test_banner_when_next_weeks_menu_is_ready(client):
    page = client.get("/week").get_data(as_text=True)
    assert "Next week's menu is ready" in page and "/week/2026-10-31" in page
    client.post("/week/2026-10-31", data={"slot-2026-11-02": "turkey-chilli"})
    assert "menu is ready" not in client.get("/week").get_data(as_text=True)


def test_no_banner_before_monday(tmp_path):
    app = create_app(f"sqlite:///{tmp_path / 'sun.db'}", today=date(2026, 10, 25))  # Sunday
    with app.app_context(), app.config["SESSION_FACTORY"]() as session:
        reset_and_seed(session)
    page = app.test_client().get("/week").get_data(as_text=True)
    assert "Week from Sat 24 Oct" in page and "menu is ready" not in page


def test_future_week_is_a_preview_until_its_monday(client):
    page = client.get("/week/2026-11-07").get_data(as_text=True)  # opens Monday 2 Nov
    assert "Preview." in page and "Monday 02 Nov" in page and 'name="slot-' not in page
    assert "Weeknight · 11 options" in page
    resp = client.post("/week/2026-11-07", data={"slot-2026-11-09": "turkey-chilli"}, follow_redirects=True)
    assert "Planning for this week opens" in resp.get_data(as_text=True)


def test_shopping_tab_follows_next_week_once_planned(client):
    assert client.get("/shopping").headers["Location"].endswith("/shopping/2026-10-24")
    client.post("/week/2026-10-31", data={"slot-2026-11-02": "turkey-chilli"})
    assert client.get("/shopping").headers["Location"].endswith("/shopping/2026-10-31")
    unopened = client.get("/shopping/2026-11-14").get_data(as_text=True)
    assert "Nothing planned yet" in unopened


def test_menu_built_too_early_is_thrown_away(tmp_path):
    """A week saved before its Monday (e.g. by an older version) and never planned becomes a preview again."""
    from db.planner import create_week
    from core.menu import Menu, week_slots
    app = create_app(f"sqlite:///{tmp_path / 'early.db'}", today=date(2026, 10, 26))
    with app.app_context(), app.config["SESSION_FACTORY"]() as session:
        reset_and_seed(session)
        create_week(session, date(2026, 11, 7), Menu(["turkey-chilli"], []), week_slots(date(2026, 11, 7)))
        session.commit()
    page = app.test_client().get("/week/2026-11-07").get_data(as_text=True)
    assert "Preview." in page and "Weeknight · 11 options" in page


def test_rate_after_cooking_and_it_shapes_next_menu(tmp_path):
    # Thursday 5 Nov: Monday's tikka has been cooked
    app = create_app(f"sqlite:///{tmp_path / 'r.db'}", today=date(2026, 11, 5))
    with app.app_context(), app.config["SESSION_FACTORY"]() as session:
        reset_and_seed(session)
    c = app.test_client()
    c.get("/week/2026-10-31")
    resp = c.post("/week/2026-10-31", data={"slot-2026-11-02": "chicken-tikka-traybake",
                                            "slot-2026-11-06": "", "open": "2026-11-02"})
    card = resp.headers["Location"]
    week = c.get("/week/2026-10-31").get_data(as_text=True)
    assert "Still to rate" in week and "Rate it ★" in week
    page = c.get(card).get_data(as_text=True)
    assert "How was it?" in page and "Not rated yet" in page
    c.post(card + "/rate", data={"dale-stars": "5", "dale-note": "Lovely", "jade-stars": "2"})
    page = c.get(card).get_data(as_text=True)
    assert "★★☆☆☆" in page and "Retired" in page and "“Lovely”" in page
    assert "Still to rate" not in c.get("/week/2026-10-31").get_data(as_text=True)
    # retired: not on a later menu, listed under Retired, and can be restored
    later = c.get("/week/2026-11-21").get_data(as_text=True)
    assert "/recipe/chicken-tikka-traybake" not in later.split("<h2>The menu</h2>")[1]
    lib = c.get("/recipes").get_data(as_text=True)
    assert lib.index("Retired") < lib.index("Chicken tikka traybake")
    c.post("/recipe/chicken-tikka-traybake/restore")
    assert "Give it another chance" not in c.get("/recipe/chicken-tikka-traybake").get_data(as_text=True)


def test_cannot_rate_before_cooking(client):
    monday = plan_two_nights(client)[1]  # today is Mon 26 Oct; the tikka is on Mon 2 Nov
    page = client.get(f"/cook/{monday}").get_data(as_text=True)
    assert "How was it?" not in page
    resp = client.post(f"/cook/{monday}/rate", data={"dale-stars": "5"}, follow_redirects=True)
    assert "once you&#39;ve cooked it" in resp.get_data(as_text=True)


def test_bad_star_value_rejected(tmp_path):
    app = create_app(f"sqlite:///{tmp_path / 'b.db'}", today=date(2026, 11, 5))
    with app.app_context(), app.config["SESSION_FACTORY"]() as session:
        reset_and_seed(session)
    c = app.test_client()
    c.get("/week/2026-10-31")
    card = c.post("/week/2026-10-31", data={"slot-2026-11-02": "turkey-chilli", "open": "2026-11-02"}).headers["Location"]
    assert c.post(card + "/rate", data={"dale-stars": "9"}).status_code == 400
