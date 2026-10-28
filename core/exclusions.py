"""The exclusion filter: hard rules for what we never get suggested.

Meals are shared, so if *either* person excludes something, any recipe that
contains it (including as a swap option) is filtered out.

A rule says "exclude this family, except these families". For example, Jade
excludes "seafood" except fish_sauce, shrimp_paste and breaded_cod. Each
family an ingredient has is checked separately: "breaded cod and prawns" has
breaded_cod (allowed) and prawn (excluded), so it's excluded.
"""

from dataclasses import dataclass, field

from core.families import ancestors, classify_name
from core.schema import Ingredient, Recipe


@dataclass(frozen=True)
class ExclusionRule:
    person: str
    family: str
    exceptions: frozenset[str] = field(default_factory=frozenset)


@dataclass(frozen=True)
class ExclusionHit:
    """Why something is excluded: whose rule, which ingredient, which family."""

    person: str
    ingredient: str
    family: str
    rule: str

    def __str__(self) -> str:
        return f"{self.ingredient} ({self.family}) - excluded by {self.person}'s '{self.rule}' rule"


def family_is_excluded(family: str, rule: ExclusionRule) -> bool:
    chain = ancestors(family)
    return rule.family in chain and not (set(chain) & rule.exceptions)


def ingredient_families(ingredient: Ingredient) -> set[str]:
    """Tagged families plus anything the keyword safety net spots in the name."""
    return set(ingredient.families) | classify_name(ingredient.name)


def check_families(name: str, families: set[str], rules: list[ExclusionRule]) -> list[ExclusionHit]:
    return [
        ExclusionHit(rule.person, name, family, rule.family)
        for family in sorted(families)
        for rule in rules
        if family_is_excluded(family, rule)
    ]


def check_name(name: str, rules: list[ExclusionRule]) -> list[ExclusionHit]:
    """Check a free-text ingredient name we have no table entry for."""
    return check_families(name, classify_name(name), rules)


def check_recipe(recipe: Recipe, catalogue: dict[str, Ingredient], rules: list[ExclusionRule]) -> list[ExclusionHit]:
    """Every exclusion hit in a recipe. An empty list means the recipe is allowed."""
    hits: list[ExclusionHit] = []
    for key in sorted(recipe.ingredient_keys()):
        ingredient = catalogue[key]  # a missing key is a data error, so let it raise
        hits += check_families(ingredient.name, ingredient_families(ingredient), rules)
    return hits


def is_allowed(recipe: Recipe, catalogue: dict[str, Ingredient], rules: list[ExclusionRule]) -> bool:
    return not check_recipe(recipe, catalogue, rules)


def is_vegetarian(recipe: Recipe, catalogue: dict[str, Ingredient]) -> bool:
    """No meat or seafood anywhere, including fish sauce."""
    for key in recipe.ingredient_keys():
        for family in ingredient_families(catalogue[key]):
            if {"meat", "seafood"} & set(ancestors(family)):
                return False
    return True
