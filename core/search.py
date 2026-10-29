"""Recipe library search: every word typed must appear somewhere in the recipe.

Searches the title, cuisine, tier, tags and ingredient names (including swap
options), so "chicken rice", "thai", "lunchbox" or "butter beans" all work.
"""

import re

from core.schema import Ingredient, Recipe


def search_text(recipe: Recipe, catalogue: dict[str, Ingredient]) -> str:
    words = [recipe.title, recipe.cuisine, recipe.tier, "weekend special" if recipe.tier == "weekend" else "",
             *recipe.tags, *(catalogue[k].name for k in sorted(recipe.ingredient_keys()))]
    return " ".join(words).lower()


def matches(text: str, query: str) -> bool:
    """True if every word of the query appears in the text (case-insensitive, ignoring punctuation)."""
    return all(word in text for word in re.findall(r"[\w-]+", query.lower()))
