"""Shared test fixtures: loaded once and reused by every test that asks for them."""

import pytest

from core.loaders import exclusion_rules, load_household, load_ingredients, load_recipes


@pytest.fixture(autouse=True)
def no_login_from_env(monkeypatch):
    """Tests don't depend on what's in your .env: login is off unless a test turns it on."""
    monkeypatch.setenv("FAMILY_PASSWORD", "")
    monkeypatch.setenv("SECRET_KEY", "")


@pytest.fixture(scope="session")
def catalogue():
    return load_ingredients()


@pytest.fixture(scope="session")
def recipes():
    return load_recipes()


@pytest.fixture(scope="session")
def rules():
    return exclusion_rules(load_household())
