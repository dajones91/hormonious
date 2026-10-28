"""Per-person portions: split the shared base and size the flexible parts.

How it works (also in PLAN.md section 4):
1. The shared base is cooked once for all portions. Each *meal* (dinner, or
   the next day's lunch) gets an equal slice of it, and each person gets their
   share of that slice: a recipe ratio, else the profile setting, else 50/50.
2. Toppings and vegetable swaps are given at their standard size.
3. The carb is sized to fit what's left of the person's targets:
   the smaller of "grams that fit the remaining kcal" and "grams that fit the
   carb limit", kept within the option's min/max and rounded to 5 g.
   If that leaves only a token amount and a vegetable swap exists, the swap is
   used instead (e.g. cauliflower rice for Jade).
"""

from dataclasses import dataclass, field

from core.nutrition import Nutrition, for_grams
from core.schema import FlexComponent, FlexOption, Ingredient, Recipe

PEOPLE = ("dale", "jade")
MEALS = ("dinner", "lunch")


@dataclass(frozen=True)
class MealTarget:
    kcal: float
    protein_min: float
    carbs_target: float  # used to size the carb
    carbs_max: float | None  # hard limit, if any
    fibre_min: float

    @property
    def carb_limit(self) -> float:
        return self.carbs_max if self.carbs_max is not None else self.carbs_target


Targets = dict[str, dict[str, MealTarget]]  # person -> meal -> target


@dataclass(frozen=True)
class FlexChoice:
    """A person's change for one component: a different option and/or grams."""

    option: str | None = None  # ingredient key of the chosen option
    grams: float | None = None


@dataclass(frozen=True)
class ComponentPortion:
    component: str
    ingredient: Ingredient
    grams: float  # weight in the ingredient's stated state (e.g. dry rice)
    sized_by: str  # "target", "standard", "swap" or "you"
    nutrition: Nutrition

    @property
    def cooked_grams(self) -> float:
        return round(self.grams * self.ingredient.cooked_yield / 5) * 5

    @property
    def weight_label(self) -> str:
        return {"dry": "dry", "raw": "raw", "cooked": "cooked"}.get(self.ingredient.state, "")


@dataclass(frozen=True)
class Plate:
    person: str
    meal: str
    share: float
    base: Nutrition
    base_added_sugar: float
    components: list[ComponentPortion] = field(default_factory=list)

    @property
    def total(self) -> Nutrition:
        total = self.base
        for c in self.components:
            total += c.nutrition
        return total

    @property
    def added_sugar(self) -> float:
        return self.base_added_sugar + sum(
            c.nutrition.sugars for c in self.components if "added_sugar" in c.ingredient.flags)


def round5(grams: float) -> float:
    return float(round(grams / 5) * 5)


def base_shares(recipe: Recipe, mode: str, fixed: dict[str, float], targets: Targets) -> dict[str, float]:
    """Each person's share of the shared base, adding up to 1."""
    if recipe.base_split:
        return dict(recipe.base_split)
    if mode == "fixed":
        return dict(fixed)
    if mode == "protein":
        protein = {p: targets[p]["dinner"].protein_min for p in PEOPLE}
        total = sum(protein.values())
        return {p: protein[p] / total for p in PEOPLE}
    return {p: 1 / len(PEOPLE) for p in PEOPLE}


def _option(comp: FlexComponent, key: str | None) -> FlexOption:
    if key is None:
        return comp.default_option
    for opt in comp.options:
        if opt.ingredient == key:
            return opt
    raise ValueError(f"'{key}' is not an option for {comp.component}")


def _portion(comp: FlexComponent, opt: FlexOption, ing: Ingredient, grams: float, sized_by: str) -> ComponentPortion:
    return ComponentPortion(comp.component, ing, grams, sized_by, for_grams(ing, grams))


def size_carb(opt: FlexOption, ing: Ingredient, target: MealTarget, used: Nutrition) -> float:
    """Grams of a carb option that fit the remaining kcal and carb limit.

    Items bought whole (wraps, pittas, rolls) are rounded to whole items, and a
    token amount (under a fifth of the standard portion) becomes none at all.
    """
    fits = [opt.max_grams]
    if ing.kcal > 0:
        fits.append((target.kcal - used.kcal) / ing.kcal * 100)
    if ing.carbs > 0:
        fits.append((target.carb_limit - used.carbs) / ing.carbs * 100)
    grams = min(max(min(fits), opt.min_grams), opt.max_grams)
    if grams < opt.standard_grams / 5:
        grams = opt.min_grams
    if ing.pack_unit == "each" and ing.unit_g:
        whole = round(grams / ing.unit_g) * ing.unit_g
        return whole if opt.min_grams <= whole <= opt.max_grams else opt.min_grams
    return round5(grams)


def build_plate(recipe: Recipe, catalogue: dict[str, Ingredient], person: str, meal: str, share: float,
                target: MealTarget, choices: dict[str, FlexChoice] | None = None) -> Plate:
    """One person's plate for one meal. `choices` is keyed by component name."""
    choices = choices or {}
    per_meal = 2 / recipe.servings  # each meal gets an equal slice of the base
    base = Nutrition()
    sugar = 0.0
    for item in recipe.shared:
        ing = catalogue[item.ingredient]
        n = for_grams(ing, item.grams * per_meal * share)
        base += n
        if "added_sugar" in ing.flags:
            sugar += n.sugars

    portions: dict[str, ComponentPortion] = {}
    carbs: list[FlexComponent] = []
    used = base
    for comp in recipe.flexible:  # toppings and fixed amounts first
        choice = choices.get(comp.component, FlexChoice())
        opt = _option(comp, choice.option)
        ing = catalogue[opt.ingredient]
        if choice.grams is not None:
            portions[comp.component] = _portion(comp, opt, ing, round5(choice.grams), "you")
        elif comp.component == "carb" and "vegetable" not in ing.flags:
            carbs.append(comp)
            continue
        else:
            portions[comp.component] = _portion(comp, opt, ing, opt.standard_grams, "standard")
        used += portions[comp.component].nutrition

    for comp in carbs:  # then the carb fills what's left
        opt = _option(comp, choices.get(comp.component, FlexChoice()).option)
        ing = catalogue[opt.ingredient]
        grams = size_carb(opt, ing, target, used)
        swap = next((o for o in comp.options if "vegetable" in catalogue[o.ingredient].flags), None)
        if grams < opt.standard_grams / 2 and swap and comp.component not in choices:
            portion = _portion(comp, swap, catalogue[swap.ingredient], swap.standard_grams, "swap")
        else:
            portion = _portion(comp, opt, ing, grams, "target")
        portions[comp.component] = portion
        used += portion.nutrition

    ordered = [portions[c.component] for c in recipe.flexible]
    return Plate(person, meal, share, base, sugar, ordered)


def plan_plates(recipe: Recipe, catalogue: dict[str, Ingredient], targets: Targets, shares: dict[str, float],
                meals: tuple[str, ...] = MEALS,
                choices: dict[tuple[str, str], dict[str, FlexChoice]] | None = None) -> list[Plate]:
    """Every plate for one cook: each person x each meal. `choices` is keyed by (person, meal)."""
    choices = choices or {}
    return [build_plate(recipe, catalogue, p, m, shares[p], targets[p][m], choices.get((p, m)))
            for m in meals for p in PEOPLE]


def meals_for_portions(portions: int) -> tuple[str, ...]:
    """4 portions = dinner + next-day lunch; 2 portions = dinner only."""
    return MEALS if portions >= 4 else ("dinner",)
