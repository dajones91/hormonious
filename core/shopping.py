"""The weekly shopping list.

1. Add up every ingredient across the week's planned nights, using the real
   per-person amounts (so if Dale has rice and Jade has cauliflower rice, both
   are on the list).
2. Merge duplicates (one line for all the garlic).
3. Round up to packs we can actually buy (e.g. "2 x 300 g pack", "3 onions").
4. Group by supermarket aisle; pantry staples are kept separate.
"""

import math
from collections import Counter, defaultdict
from dataclasses import dataclass, field

from core.portions import Plate, recipe_fraction
from core.schema import Ingredient, Recipe

AISLE_ORDER = [
    "Fruit & veg", "Meat & poultry", "Fish", "Dairy & eggs", "Chilled", "Bakery", "Frozen",
    "Rice, pasta & grains", "Tins & jars", "World foods", "Nuts & seeds", "Herbs & spices",
    "Oils & condiments", "Stock & gravy",
]


@dataclass(frozen=True)
class PlannedCook:
    recipe: Recipe
    portions: int
    plates: list[Plate]


@dataclass
class ShoppingItem:
    ingredient: Ingredient
    grams: float  # total needed
    recipes: list[str] = field(default_factory=list)
    staple: bool = False

    @property
    def key(self) -> str:
        return self.ingredient.key

    @property
    def needed(self) -> float:
        """Grams, or a whole count for things bought individually."""
        ing = self.ingredient
        if ing.pack_unit == "each" and ing.unit_g:
            return math.ceil(round(self.grams / ing.unit_g, 2))
        return math.ceil(self.grams)

    @property
    def packs(self) -> list[float]:
        ing = self.ingredient
        if ing.pack_unit == "each" and 1 in ing.packs:  # sold loose: buy exactly what's needed
            return [1.0] * int(self.needed)
        return choose_packs(self.needed, ing.packs)

    @property
    def needed_text(self) -> str:
        return f"need {self.needed:.0f}" if self.ingredient.pack_unit == "each" else f"need {self.needed:.0f} g"

    @property
    def buy_text(self) -> str:
        return packs_text(self.ingredient, self.packs)


def choose_packs(needed: float, sizes: list[float]) -> list[float]:
    """The packs to buy: as little over what's needed as possible, then the fewest packs.

    e.g. need 450 g with packs of 300/650/1000 -> [650]; need 480 g of 240 g tins -> [240, 240].
    """
    sizes = sorted({int(s) for s in sizes if s > 0})
    target = math.ceil(needed)
    if target <= 0:
        return []
    if not sizes:
        return [target]
    limit = target + max(sizes)
    fewest = [0] + [math.inf] * limit  # fewest packs to make exactly n
    last = [0] * (limit + 1)
    for n in range(1, limit + 1):
        for s in sizes:
            if s <= n and fewest[n - s] + 1 < fewest[n]:
                fewest[n], last[n] = fewest[n - s] + 1, s
    best = min((n for n in range(target, limit + 1) if fewest[n] < math.inf), key=lambda n: (n, fewest[n]))
    chosen = []
    while best:
        chosen.append(float(last[best]))
        best -= last[best]
    return sorted(chosen, reverse=True)


def _plural(word: str, n: int) -> str:
    if n == 1:
        return word
    return word + ("es" if word.endswith(("sh", "ch", "x", "s")) else "s")


def packs_text(ing: Ingredient, packs: list[float]) -> str:
    """'2 x 300 g pack', '3 onions', '1 x box of 6', '2 x 400 g tin'."""
    if not packs:
        return ""
    parts = []
    for size, n in sorted(Counter(packs).items(), reverse=True):
        if ing.pack_unit == "each":
            if size == 1:
                parts.append(f"{n} {_plural(ing.pack_label, n)}")
            else:
                parts.append(f"{n} x {ing.pack_label} of {size:.0f}")
        elif any(ch.isdigit() for ch in ing.pack_label):  # label already says the size, e.g. "400 g tin"
            parts.append(f"{n} x {ing.pack_label}")
        else:
            parts.append(f"{n} x {size:.0f} g {ing.pack_label}")
    return " + ".join(parts)


def build_list(cooks: list[PlannedCook], catalogue: dict[str, Ingredient], pantry: set[str]) -> list[ShoppingItem]:
    grams: dict[str, float] = defaultdict(float)
    used_in: dict[str, list[str]] = defaultdict(list)

    def add(key: str, amount: float, title: str) -> None:
        if amount <= 0:
            return
        grams[key] += amount
        if title not in used_in[key]:
            used_in[key].append(title)

    for cook in cooks:
        scale = recipe_fraction(cook.recipe, cook.plates)  # only the plates actually being eaten
        for item in cook.recipe.shared:
            add(item.ingredient, item.grams * scale, cook.recipe.title)
        for plate in cook.plates:
            for c in plate.components:
                add(c.ingredient.key, c.grams, cook.recipe.title)

    return [ShoppingItem(catalogue[k], g, used_in[k], staple=k in pantry) for k, g in grams.items()]


def group_by_aisle(items: list[ShoppingItem]) -> list[tuple[str, list[ShoppingItem]]]:
    by_aisle: dict[str, list[ShoppingItem]] = defaultdict(list)
    for item in items:
        by_aisle[item.ingredient.aisle].append(item)
    order = {a: i for i, a in enumerate(AISLE_ORDER)}
    return [(aisle, sorted(by_aisle[aisle], key=lambda i: i.ingredient.name))
            for aisle in sorted(by_aisle, key=lambda a: (order.get(a, len(order)), a))]


def as_text(items: list[ShoppingItem], title: str, ticked: set[str] = frozenset()) -> str:
    """Plain text to paste into a message. Pantry staples are listed at the end."""
    lines = [title, ""]
    for aisle, group in group_by_aisle([i for i in items if not i.staple]):
        lines.append(aisle.upper())
        for i in group:
            mark = "[x]" if i.key in ticked else "[ ]"
            lines.append(f"{mark} {i.ingredient.name}: {i.buy_text}")
        lines.append("")
    staples = sorted(i.ingredient.name for i in items if i.staple)
    if staples:
        lines.append("CHECK THE CUPBOARD: " + ", ".join(staples))
    return "\n".join(lines).rstrip() + "\n"
