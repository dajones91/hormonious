"""Family password login, 'who are you', rating as yourself, and production safety checks."""

from datetime import date

import pytest

from app import auth, create_app
from db.repo import reset_and_seed


@pytest.fixture
def app(tmp_path):
    auth._failures.clear()
    app = create_app(f"sqlite:///{tmp_path / 'auth.db'}", today=date(2026, 11, 5), family_password="beans on toast")
    with app.app_context(), app.config["SESSION_FACTORY"]() as s:
        reset_and_seed(s)
    return app


def log_in(client, person="dale"):
    client.post("/login", data={"password": "beans on toast"})
    client.post("/who", data={"person": person})


def test_pages_need_login(app):
    c = app.test_client()
    for path in ("/week", "/recipes", "/shopping", "/profiles", "/recipe/turkey-chilli"):
        resp = c.get(path)
        assert resp.status_code == 302 and "/login" in resp.headers["Location"], path
    assert c.post("/recipes/generate", data={"tier": "weeknight"}).status_code == 302  # forms too


def test_public_bits_stay_public(app):
    c = app.test_client()
    assert c.get("/login").status_code == 200
    assert c.get("/static/style.css").status_code == 200
    manifest = c.get("/manifest.webmanifest")
    assert manifest.status_code == 200 and manifest.json["display"] == "standalone"
    assert manifest.mimetype == "application/manifest+json"
    assert c.get("/static/icons/apple-touch-icon.png").status_code == 200


def test_wrong_password(app):
    page = app.test_client().post("/login", data={"password": "nope"}).get_data(as_text=True)
    assert "not the right password" in page


def test_lockout_after_too_many_wrong_passwords(app):
    c = app.test_client()
    for _ in range(auth.MAX_FAILURES):
        c.post("/login", data={"password": "nope"})
    resp = c.post("/login", data={"password": "beans on toast"})  # even the right one, for now
    assert resp.status_code == 429 and "wait 15 minutes" in resp.get_data(as_text=True)


def test_login_then_who_then_back_where_you_were(app):
    c = app.test_client()
    resp = c.get("/recipes")
    assert "next=" in resp.headers["Location"]
    resp = c.post(resp.headers["Location"], data={"password": "beans on toast"})
    assert "/who" in resp.headers["Location"]
    resp = c.post(resp.headers["Location"], data={"person": "jade"})
    assert resp.headers["Location"].endswith("/recipes")
    assert c.get("/recipes").status_code == 200
    profiles = c.get("/profiles").get_data(as_text=True)
    assert 'This device is <span class="who jade">Jade</span>' in profiles


def test_next_cannot_send_you_to_another_site(app):
    c = app.test_client()
    resp = c.post("/login?next=//evil.example.com", data={"password": "beans on toast"})
    resp = c.post(resp.headers["Location"], data={"person": "dale"})
    assert "evil" not in resp.headers["Location"]


def test_stays_logged_in_and_cookie_is_safe(app):
    c = app.test_client()
    resp = c.post("/login", data={"password": "beans on toast"})
    cookie = resp.headers["Set-Cookie"]
    assert "HttpOnly" in cookie and "SameSite=Lax" in cookie and "Expires=" in cookie


def test_logout(app):
    c = app.test_client()
    log_in(c)
    c.post("/logout")
    assert "/login" in c.get("/week").headers["Location"]


def test_you_rate_as_yourself(app):
    c = app.test_client()
    log_in(c, "jade")
    c.get("/week/2026-10-31")
    card = c.post("/week/2026-10-31", data={"slot-2026-11-02": "turkey-chilli", "open": "2026-11-02"}).headers["Location"]
    page = c.get(card).get_data(as_text=True)
    assert 'name="jade-stars"' in page and 'name="dale-stars"' not in page
    c.post(card + "/rate", data={"jade-stars": "5", "dale-stars": "1"})  # can't rate for Dale
    page = c.get(card).get_data(as_text=True)
    assert "★★★★★" in page  # only Jade's 5 counted


def test_no_login_when_no_password_set(tmp_path):
    app = create_app(f"sqlite:///{tmp_path / 'open.db'}", family_password="change-me")
    assert app.config["FAMILY_PASSWORD"] is None
    assert app.test_client().get("/login").status_code == 302  # straight to the app


def test_production_refuses_placeholder_secrets(tmp_path, monkeypatch):
    monkeypatch.setenv("SECRET_KEY", "change-me")
    with pytest.raises(RuntimeError, match="SECRET_KEY"):
        create_app(f"sqlite:///{tmp_path / 'p.db'}", family_password="real one", production=True)
    monkeypatch.setenv("SECRET_KEY", "a" * 64)
    app = create_app(f"sqlite:///{tmp_path / 'p.db'}", family_password="real one", production=True)
    assert app.config["SESSION_COOKIE_SECURE"] is True


def test_migrations_build_a_fresh_database(tmp_path):
    import sqlite3
    create_app(f"sqlite:///{tmp_path / 'fresh.db'}")
    tables = {r[0] for r in sqlite3.connect(tmp_path / "fresh.db").execute("select name from sqlite_master")}
    assert {"recipe", "plan_slot", "rating", "slot_eaters", "alembic_version"} <= tables
