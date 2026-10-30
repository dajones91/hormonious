"""What to cook in total for one night, and how to plate it for each person.

Cooking quantities cover every portion being made (4 = 2 dinners + 2 lunches).
The plating guide says how to share the pot, and gives each person's flexible
part in grams, labelled dry/raw, with the cooked weight where it changes.
"""

import re
from collections import defaultdict
from dataclasses import dataclass

from core.portions import Plate
from core.schema import Ingredient, Recipe


def fmt_g(grams: float) -> str:
    return f"{grams:.0f} g"


def amount_text(ingredient: Ingredient, grams: float) -> str:
    """'130 g', or '2 wholemeal tortilla wraps' for things bought whole."""
    if ingredient.pack_unit == "each" and ingredient.unit_g and grams > 0:
        count = grams / ingredient.unit_g
        if abs(count - round(count)) < 0.05:
            return f"{round(count)} x {ingredient.name.lower()}"
    label = f" {ingredient.state}" if ingredient.state in ("dry", "raw") and ingredient.cooked_yield != 1 else ""
    return f"{fmt_g(grams)}{label} {ingredient.name.lower()}"


@dataclass(frozen=True)
class CookLine:
    ingredient: Ingredient
    grams: float
    text: str  # e.g. "2 x 400 g tins, drained chopped tomatoes"
    note: str | None = None


@dataclass(frozen=True)
class PlateShare:
    person: str
    meal: str
    grams: float
    percent: int  # of what's cooked


@dataclass(frozen=True)
class FlexCookLine:
    component: str
    ingredient: Ingredient
    grams: float  # total to cook, in the ingredient's stated state
    shares: list[PlateShare]

    @property
    def cooked_grams(self) -> float:
        return round(self.grams * self.ingredient.cooked_yield / 5) * 5

    @property
    def text(self) -> str:
        cooked = f" (about {fmt_g(self.cooked_grams)} cooked)" if self.ingredient.cooked_yield != 1 else ""
        return amount_text(self.ingredient, self.grams) + cooked


def cook_base(recipe: Recipe, catalogue: dict[str, Ingredient], scale: float) -> list[CookLine]:
    """The shared base scaled for the plates being cooked (see recipe_fraction). Friendly amounts are kept when unscaled."""
    scale = round(scale, 4)
    lines = []
    for item in recipe.shared:
        ing = catalogue[item.ingredient]
        grams = item.grams * scale
        if scale == 1 and item.display and re.fullmatch(r"[\d/ ]+", item.display):
            text = f"{item.display} x {ing.name.lower()}"  # "2 x red peppers", not "2 red peppers"
        elif scale == 1 and item.display:
            text = f"{item.display} {ing.name.lower()}"
        elif item.display:
            text = f"{fmt_g(grams)} {ing.name.lower()} (scaled from {item.display})"
        else:
            text = f"{fmt_g(grams)} {ing.name.lower()}"
        lines.append(CookLine(ing, grams, text, item.note))
    return lines


def cook_flex(plates: list[Plate]) -> list[FlexCookLine]:
    """Flexible parts to cook, combining people who chose the same thing."""
    totals: dict[tuple[str, str], list] = defaultdict(list)
    ingredients: dict[str, Ingredient] = {}
    for plate in plates:
        for c in plate.components:
            if c.grams > 0:
                totals[(c.component, c.ingredient.key)].append((plate, c.grams))
                ingredients[c.ingredient.key] = c.ingredient
    lines = []
    for (component, key), entries in totals.items():
        total = sum(g for _, g in entries)
        shares = [PlateShare(p.person, p.meal, g, round(g / total * 100)) for p, g in entries]
        lines.append(FlexCookLine(component, ingredients[key], total, shares))
    return lines


def pot_shares(plates: list[Plate]) -> dict[tuple[str, str], int]:
    """Each plate's percentage of the shared base pot, e.g. Dale dinner 25%."""
    total = sum(p.share for p in plates)
    return {(p.person, p.meal): round(p.share / total * 100) for p in plates}
