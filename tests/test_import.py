"""Recipe import from text or a photo, tested with a fake AI (no API key, nothing spent)."""

import base64
from datetime import date
from io import BytesIO

import pytest
from PIL import Image
from werkzeug.datastructures import MultiDict

from ai.generate import AiError
from ai.importer import ImportAnswer, MAX_IMAGE_SIDE, prepare_image
from app import create_app
from app.import_form import recipe_from_form
from db.models import ImportDraftRow
from db.repo import get_recipe, reset_and_seed


def chilli_answer(title="Mum's beef chilli", extra_shared=(), new_ingredients=()):
    return ImportAnswer(is_recipe=True, message="Scaled from 6 servings to 4.", new_ingredients=list(new_ingredients),
                        recipe={
        "title": title, "tier": "weeknight", "cuisine": "Mexican", "spice": 2, "active_min": 15, "total_min": 40,
        "tags": ["high-protein", "lunchbox-friendly"],
        "shared": [
            {"ingredient": "turkey_mince", "grams": 750, "display": "750 g", "note": None},
            {"ingredient": "onion", "grams": 150, "display": "1", "note": "chopped"},
            {"ingredient": "red_pepper", "grams": 320, "display": "2", "note": None},
            {"ingredient": "kidney_beans", "grams": 480, "display": "2 x 400 g tins, drained", "note": None},
            {"ingredient": "chopped_tomatoes", "grams": 800, "display": "2 x 400 g tins", "note": None},
            {"ingredient": "olive_oil", "grams": 14, "display": "1 tbsp", "note": None},
            {"ingredient": "smoked_paprika", "grams": 6, "display": "2 tsp", "note": None},
            *extra_shared,
        ],
        "flexible": [{"component": "carb", "cook_note": "Boil the rice for 25 min.", "options": [
            {"ingredient": "white_basmati", "standard_grams": 60, "min_grams": 0, "max_grams": 110, "default": True},
            {"ingredient": "brown_basmati", "standard_grams": 60, "min_grams": 0, "max_grams": 110, "default": False},
            {"ingredient": "cauliflower_rice", "standard_grams": 150, "min_grams": 0, "max_grams": 300, "default": False},
        ]}],
        "steps": ["Brown the mince.", "Add everything else and simmer for 25 minutes.",
                  "Plate using the plating guide."],
        "reheat_note": "Microwave until piping hot.",
    })


class FakeImport:
    def __init__(self, answer):
        self.answer = answer
        self.calls = []

    def __call__(self, system, text, image_b64):
        self.calls.append((system, text, image_b64))
        return self.answer, {"input": 5000, "output": 2000}


@pytest.fixture
def app(tmp_path):
    app = create_app(f"sqlite:///{tmp_path / 'imp.db'}", today=date(2026, 10, 26))
    with app.app_context(), app.config["SESSION_FACTORY"]() as s:
        reset_and_seed(s)
    return app


def png_bytes(size=(3000, 2000)):
    out = BytesIO()
    Image.new("RGB", size, "white").save(out, format="PNG")
    return out.getvalue()


def start_import(app, answer, **data):
    app.config["IMPORT_CALL"] = fake = FakeImport(answer)
    client = app.test_client()
    resp = client.post("/recipes/import", data={"text": "Mum's chilli: mince, beans...", **data},
                       content_type="multipart/form-data")
    return client, resp, fake


def test_text_import_opens_review_with_checks(app):
    client, resp, fake = start_import(app, chilli_answer(), source_url="https://example.com/chilli")
    assert resp.status_code == 302 and "/recipes/import/" in resp.headers["Location"]
    page = client.get(resp.headers["Location"]).get_data(as_text=True)
    assert "Check your recipe" in page and "Scaled from 6 servings to 4." in page
    assert 'value="Mum&#39;s beef chilli"' in page and "Basmati rice" in page
    assert "Dale" in page and "Jade" in page  # per-person plates
    assert "Mum's chilli" in fake.calls[0][1] and "Ingredient table" in fake.calls[0][0]


def form_from_review(page_data: dict, **overrides) -> dict:
    """The review form as the browser would send it, for the chilli answer."""
    form = {"title": "Mum's beef chilli", "tier": "weeknight", "cuisine": "Mexican", "active_min": "15",
            "total_min": "40", "spice": "2", "tags": "high-protein, lunchbox-friendly",
            "steps": "Brown the mince.\nSimmer.\nPlate using the plating guide.", "reheat_note": "Microwave.",
            "flex-0-component": "carb", "flex-0-cook_note": "", "flex-0-default": "1"}
    for i, (key, grams) in enumerate([("turkey_mince", 750), ("onion", 150), ("red_pepper", 320),
                                      ("kidney_beans", 480), ("chopped_tomatoes", 800), ("olive_oil", 14),
                                      ("smoked_paprika", 6)]):
        form.update({f"shared-{i}-ingredient": key, f"shared-{i}-grams": str(grams),
                     f"shared-{i}-display": "", f"shared-{i}-note": ""})
    for j, (key, std, mx) in enumerate([("white_basmati", 60, 110), ("brown_basmati", 60, 110),
                                        ("cauliflower_rice", 150, 300)]):
        form.update({f"flex-0-opt-{j}-ingredient": key, f"flex-0-opt-{j}-standard": str(std),
                     f"flex-0-opt-{j}-min": "0", f"flex-0-opt-{j}-max": str(mx)})
    form.update(page_data)
    form.update(overrides)
    return form


def test_edit_and_save(app):
    client, resp, _ = start_import(app, chilli_answer(), source_url="https://example.com/chilli")
    review = resp.headers["Location"]
    form = form_from_review({}, **{"title": "Mum's turkey chilli", "shared-1-grams": "300",
                                   "shared-7-ingredient": "spinach", "shared-7-grams": "200",
                                   "action": "save"})
    saved = client.post(review, data=form, follow_redirects=True).get_data(as_text=True)
    assert "Recipe added to your library" in saved and "Mum&#39;s turkey chilli" in saved
    with app.config["SESSION_FACTORY"]() as s:
        r = get_recipe(s, "mum-s-turkey-chilli")
        assert r.source == "imported" and r.source_url == "https://example.com/chilli"
        assert {i.ingredient: i.grams for i in r.shared}["onion"] == 300
        assert "spinach" in r.ingredient_keys()
        assert r.flexible[0].default_option.ingredient == "brown_basmati"  # default radio = option 1
        assert s.query(ImportDraftRow).count() == 0  # draft deleted after saving


def test_check_my_changes_keeps_draft(app):
    client, resp, _ = start_import(app, chilli_answer())
    review = resp.headers["Location"]
    client.post(review, data=form_from_review({}, title="Edited title", action="check"))
    page = client.get(review).get_data(as_text=True)
    assert 'value="Edited title"' in page


def test_excluded_ingredient_is_warned_but_can_be_saved(app):
    salmon = {"ingredient": "salmon_fillet", "grams": 300, "display": None, "note": None}
    client, resp, _ = start_import(app, chilli_answer(extra_shared=[salmon]))
    page = client.get(resp.headers["Location"]).get_data(as_text=True)
    assert "salmon" in page.lower() and "won't be suggested on menus" in page


def test_bad_edits_are_explained(app):
    client, resp, _ = start_import(app, chilli_answer())
    review = resp.headers["Location"]
    page = client.post(review, data=form_from_review({}, **{"shared-0-grams": "lots", "action": "save"}),
                       follow_redirects=True).get_data(as_text=True)
    assert "isn&#39;t a number" in page
    with app.config["SESSION_FACTORY"]() as s:
        assert s.query(ImportDraftRow).count() == 1


def test_discard(app):
    client, resp, _ = start_import(app, chilli_answer())
    client.post(resp.headers["Location"], data={"action": "discard"})
    assert "already been saved or discarded" in client.get(resp.headers["Location"], follow_redirects=True).get_data(as_text=True)


def test_not_a_recipe(app):
    nope = ImportAnswer(is_recipe=False, message="This is a shopping receipt, not a recipe.", recipe=None,
                        new_ingredients=[])
    client, resp, _ = start_import(app, nope)
    page = client.get(resp.headers["Location"]).get_data(as_text=True)
    assert "shopping receipt" in page


def test_photo_is_shrunk_sent_and_not_stored(app):
    app.config["IMPORT_CALL"] = fake = FakeImport(chilli_answer())
    client = app.test_client()
    resp = client.post("/recipes/import", data={"text": "", "photo": (BytesIO(png_bytes()), "card.png")},
                       content_type="multipart/form-data")
    assert "/recipes/import/" in resp.headers["Location"]
    _, text, image_b64 = fake.calls[0]
    sent = Image.open(BytesIO(base64.b64decode(image_b64)))
    assert sent.format == "JPEG" and max(sent.size) == MAX_IMAGE_SIDE
    with app.config["SESSION_FACTORY"]() as s:
        draft = s.query(ImportDraftRow).one()
        assert image_b64[:50] not in str(draft.data)  # only the extracted recipe is kept


def test_unreadable_photo(app):
    with pytest.raises(AiError, match="JPEG or PNG"):
        prepare_image(b"not an image at all")
    app.config["IMPORT_CALL"] = FakeImport(chilli_answer())
    page = app.test_client().post("/recipes/import", data={"photo": (BytesIO(b"nope"), "x.heic")},
                                  content_type="multipart/form-data", follow_redirects=True)
    assert "Couldn&#39;t read that image" in page.get_data(as_text=True)


def test_nothing_to_import(app):
    page = app.test_client().post("/recipes/import", data={"text": "  "}, content_type="multipart/form-data",
                                  follow_redirects=True)
    assert "Paste some recipe text or choose a photo" in page.get_data(as_text=True)


def test_form_parsing_drops_blank_and_removed_rows():
    form = MultiDict({
        "title": "T", "tier": "weeknight", "cuisine": "", "active_min": "10", "total_min": "20", "spice": "1",
        "tags": "a, b,", "steps": "one\n\n two \n", "reheat_note": "x",
        "shared-0-ingredient": "onion", "shared-0-grams": "150",
        "shared-1-ingredient": "garlic", "shared-1-grams": "10", "shared-1-remove": "on",
        "shared-2-ingredient": "", "shared-2-grams": "",
        "flex-0-component": "carb", "flex-0-opt-0-ingredient": "brown_basmati", "flex-0-opt-0-standard": "60",
        "flex-0-opt-0-min": "0", "flex-0-opt-0-max": "100",
        "flex-1-component": "topping", "flex-1-opt-0-ingredient": "",
    })
    recipe, errors = recipe_from_form(form)
    assert errors == []
    assert [i["ingredient"] for i in recipe["shared"]] == ["onion"]
    assert recipe["tags"] == ["a", "b"] and recipe["steps"] == ["one", "two"] and recipe["cuisine"] == "Home"
    assert len(recipe["flexible"]) == 1 and recipe["flexible"][0]["options"][0]["default"] is True
