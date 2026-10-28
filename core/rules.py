"""Nutrition and recipe rules, checked against each person's plated portion.

A "fail" keeps a recipe off the menu. A "warn" is shown but doesn't block.
Weekend specials follow the rules loosely, so their nutrition fails become warnings.
"""

from dataclasses import dataclass

from core.portions import MealTarget, Plate, Targets
from core.schema import Ingredient, Recipe


@dataclass(frozen=True)
class RuleSettings:
    added_sugar_max_g: float = 5
    weeknight_max_min: int = 45
    weekend_max_min: int = 90
    kcal_over_warn: float = 0.15  # warn when a plate is over its kcal target by more than 15%


@dataclass(frozen=True)
class Issue:
    level: str  # "fail" or "warn"
    message: str
    person: str | None = None
    meal: str | None = None

    def __str__(self) -> str:
        who = f"{self.person.title()} {self.meal}: " if self.person else ""
        return f"{who}{self.message}"


def check_plate(plate: Plate, target: MealTarget, settings: RuleSettings) -> list[Issue]:
    # Compare the rounded values we show, so "fibre 8 g" never fails an 8 g target.
    n = plate.total.rounded()
    issues = []

    def add(level, msg):
        issues.append(Issue(level, msg, plate.person, plate.meal))

    if n.protein < target.protein_min:
        add("fail", f"protein {n.protein:.0f} g, target at least {target.protein_min:.0f} g")
    if n.fibre < target.fibre_min:
        add("fail", f"fibre {n.fibre:.0f} g, target at least {target.fibre_min:.0f} g")
    if target.carbs_max is not None and n.carbs > target.carbs_max:
        add("fail", f"carbs {n.carbs:.0f} g, limit {target.carbs_max:.0f} g")
    if round(plate.added_sugar) > settings.added_sugar_max_g:
        add("fail", f"added sugar {plate.added_sugar:.0f} g, limit {settings.added_sugar_max_g:.0f} g")
    if n.kcal > target.kcal * (1 + settings.kcal_over_warn):
        add("warn", f"{n.kcal:.0f} kcal, target {target.kcal:.0f} (shared base is large for this target)")
    return issues


def check_structure(recipe: Recipe, catalogue: dict[str, Ingredient], settings: RuleSettings) -> list[Issue]:
    """Rules about the recipe itself, not anyone's portion."""
    issues = []
    limit = settings.weeknight_max_min if recipe.tier == "weeknight" else settings.weekend_max_min
    if recipe.total_min > limit:
        issues.append(Issue("fail", f"takes {recipe.total_min} min, limit {limit}"))

    flags = set().union(*(catalogue[i.ingredient].flags for i in recipe.shared))
    for needed, label in (("protein", "a protein"), ("vegetable", "vegetables"), ("healthy_fat", "a healthy fat")):
        if needed not in flags:
            issues.append(Issue("fail", f"no {label} in the shared base"))

    for comp in recipe.flexible:
        opts = [catalogue[o.ingredient] for o in comp.options]
        if any("refined_carb" in i.flags for i in opts) and not any(i.gi == "low" for i in opts):
            issues.append(Issue("fail", f"refined {comp.component} with no low-GI swap"))
    if any("refined_carb" in catalogue[i.ingredient].flags for i in recipe.shared):
        issues.append(Issue("fail", "refined carb in the shared base (can't be swapped)"))

    if recipe.tier == "weeknight" and "lunchbox-friendly" not in recipe.tags:
        issues.append(Issue("fail", "weeknight recipes must be lunchbox-friendly"))
    return issues


def validate(recipe: Recipe, catalogue: dict[str, Ingredient], plates: list[Plate], targets: Targets,
             settings: RuleSettings) -> list[Issue]:
    issues = check_structure(recipe, catalogue, settings)
    for plate in plates:
        for issue in check_plate(plate, targets[plate.person][plate.meal], settings):
            if recipe.tier == "weekend" and issue.level == "fail":
                issue = Issue("warn", issue.message + " (weekend: allowed)", issue.person, issue.meal)
            issues.append(issue)
    return issues


def passes(issues: list[Issue]) -> bool:
    return not any(i.level == "fail" for i in issues)
