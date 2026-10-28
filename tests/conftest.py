"""Shared test fixtures: loaded once and reused by every test that asks for them."""

import pytest

from core.loaders import exclusion_rules, load_household, load_ingredients, load_recipes


@pytest.fixture(scope="session")
def catalogue():
    return load_ingredients()


@pytest.fixture(scope="session")
def recipes():
    return load_recipes()


@pytest.fixture(scope="session")
def rules():
    return exclusion_rules(load_household())
