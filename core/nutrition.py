"""Nutrition sums. Values in the ingredient table are per 100 g."""

from dataclasses import dataclass, fields

from core.schema import Ingredient, Recipe, RecipeItem


@dataclass(frozen=True)
class Nutrition:
    kcal: float = 0
    protein: float = 0
    carbs: float = 0
    sugars: float = 0
    fibre: float = 0
    fat: float = 0

    def __add__(self, other: "Nutrition") -> "Nutrition":
        return Nutrition(*(getattr(self, f.name) + getattr(other, f.name) for f in fields(self)))

    def scale(self, factor: float) -> "Nutrition":
        return Nutrition(*(getattr(self, f.name) * factor for f in fields(self)))

    def rounded(self) -> "Nutrition":
        """Display rounding: kcal to the nearest 10, everything else to whole grams."""
        return Nutrition(round(self.kcal, -1), *(round(getattr(self, f.name)) for f in fields(self)[1:]))


def for_grams(ingredient: Ingredient, grams: float) -> Nutrition:
    per_100 = Nutrition(ingredient.kcal, ingredient.protein, ingredient.carbs,
                        ingredient.sugars, ingredient.fibre, ingredient.fat)
    return per_100.scale(grams / 100)


def items_total(items: list[RecipeItem], catalogue: dict[str, Ingredient]) -> Nutrition:
    total = Nutrition()
    for item in items:
        total += for_grams(catalogue[item.ingredient], item.grams)
    return total


def base_per_portion(recipe: Recipe, catalogue: dict[str, Ingredient]) -> Nutrition:
    """The shared base divided evenly over all servings (no per-person split yet)."""
    return items_total(recipe.shared, catalogue).scale(1 / recipe.servings)
