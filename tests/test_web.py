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


def test_bad_profile_input_is_not_saved(client):
    page = client.post("/profiles", data={"dale-dinner-kcal": "lots"}, follow_redirects=True).get_data(as_text=True)
    assert "Not saved" in page
