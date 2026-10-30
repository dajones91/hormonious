"""Brings the core rules and the database together for the web pages and commands."""

from dataclasses import dataclass
from datetime import date

from sqlalchemy.orm import Session

from ai.generate import Call, GenerationResult, call_claude, generate_recipe, system_prompt
from core.exclusions import ExclusionHit, check_recipe
from core.menu import Menu, build_menu, menu_is_ready, week_slots
from core.portions import Eaters, Plate, Targets, base_shares, plan_plates
from core.ratings import DEFAULT_COOLDOWN_WEEKS, household_rating
from core.rules import Issue, RuleSettings, passes, validate
from core.schema import Ingredient, Recipe
from core.shopping import PlannedCook, ShoppingItem, build_list
from db.models import PlanSlotRow, WeekRow
from db.repo import (all_titles_and_slugs, create_week, get_catalogue, get_choices, get_exclusion_notes,
                     get_eaters, get_exclusion_rules, get_pantry, get_ratings, get_recipe, get_recipes, get_restores, get_settings,
                     get_targets, get_week, last_cooked, save_ingredient, save_recipe)


@dataclass
class RecipeCheck:
    recipe: Recipe
    plates: list[Plate]
    issues: list[Issue]
    exclusions: list[ExclusionHit]

    @property
    def ok(self) -> bool:
        return not self.exclusions and passes(self.issues)


@dataclass
class Context:
    """Everything needed to check recipes, loaded once per request."""

    catalogue: dict[str, Ingredient]
    targets: Targets
    settings: dict
    rule_settings: RuleSettings

    def plates(self, recipe: Recipe, eaters: Eaters | None = None, choices=None) -> list[Plate]:
        """Plates for whoever's eating (both of us, dinner and lunch, by default)."""
        shares = base_shares(recipe, self.settings["split_mode"], self.settings["fixed_split"], self.targets)
        return plan_plates(recipe, self.catalogue, self.targets, shares, choices=choices, eaters=eaters,
                           same_lunch=self.settings.get("same_lunch_as_dinner", True))

    def check(self, recipe: Recipe, rules, eaters: Eaters | None = None, choices=None) -> RecipeCheck:
        plates = self.plates(recipe, eaters, choices)
        issues = validate(recipe, self.catalogue, plates, self.targets, self.rule_settings)
        return RecipeCheck(recipe, plates, issues, check_recipe(recipe, self.catalogue, rules))


def load_context(session: Session) -> Context:
    settings = get_settings(session)
    rule_settings = RuleSettings(**{k: settings[k] for k in ("added_sugar_max_g", "weeknight_max_min",
                                                             "weekend_max_min") if k in settings})
    return Context(get_catalogue(session), get_targets(session), settings, rule_settings)


def check_all(session: Session, ctx: Context | None = None) -> list[RecipeCheck]:
    ctx = ctx or load_context(session)
    rules = get_exclusion_rules(session)
    return [ctx.check(r, rules) for r in get_recipes(session)]


def household_stars(session: Session) -> dict[str, int | None]:
    """Each recipe's household rating (the lower of our latest ratings since any restore)."""
    restores = get_restores(session)
    return {slug: household_rating(ratings, restores.get(slug)) for slug, ratings in get_ratings(session).items()}


def make_menu(session: Session, start: date) -> Menu:
    ctx = load_context(session)
    eligible = [c.recipe for c in check_all(session, ctx) if c.ok]
    cooldowns = {int(k): v for k, v in ctx.settings.get("cooldown_weeks", {}).items()} or DEFAULT_COOLDOWN_WEEKS
    return build_menu(eligible, start, last_cooked(session, start),
                      ctx.settings["weeknight_options"], ctx.settings["weekend_options"],
                      stars=household_stars(session), cooldowns=cooldowns,
                      favourite_share=ctx.settings.get("favourite_share", 0.6))


def ensure_week(session: Session, start: date, today: date) -> WeekRow | None:
    """Get the week's menu and plan.

    The menu is built and saved from the Monday before the week starts, once the
    current week's plan is settled. Before then there's nothing to plan: returns None
    (use `make_menu` for an unsaved preview).
    """
    week = get_week(session, start)
    if week is not None and not menu_is_ready(start, today) and not has_plan(week):
        session.delete(week)  # built too early (before Monday) and never planned: rebuild on its Monday
        session.commit()
        week = None
    if week is None and menu_is_ready(start, today):
        ctx = load_context(session)
        week = create_week(session, start, make_menu(session, start),
                           week_slots(start, ctx.settings["friday_plan"]))
        session.commit()
    return week


def has_plan(week: WeekRow | None) -> bool:
    return week is not None and any(s.recipe_slug or s.no_cook for s in week.slots)


def week_cooks(session: Session, week: WeekRow, ctx: Context) -> list[tuple[PlanSlotRow, PlannedCook]]:
    """Every planned cook in the week, with each person's actual portions."""
    cooks = []
    for slot in week.slots:
        if slot.recipe_slug:
            recipe = get_recipe(session, slot.recipe_slug)
            plates = ctx.plates(recipe, get_eaters(session, slot), get_choices(slot))
            cooks.append((slot, PlannedCook(recipe, len(plates), plates)))
    return cooks


def shopping_list(session: Session, week: WeekRow) -> list[ShoppingItem]:
    ctx = load_context(session)
    cooks = [cook for _, cook in week_cooks(session, week, ctx)]
    return build_list(cooks, ctx.catalogue, get_pantry(session))


def targets_text(targets: Targets, same_lunch: bool) -> str:
    lines = []
    for person, meals in targets.items():
        for meal, t in meals.items():
            carbs = f"carbs at most {t.carbs_max:.0f} g" if t.carbs_max is not None else f"carbs about {t.carbs_target:.0f} g"
            lines.append(f"- {person.title()} {meal}: about {t.kcal:.0f} kcal, protein at least {t.protein_min:.0f} g, "
                         f"{carbs}, fibre at least {t.fibre_min:.0f} g")
    if same_lunch:
        lines.append("Each person's lunch box is the same as their dinner (sized halfway between the two targets).")
    return "\n".join(lines)


def generate_and_save(session: Session, tier: str, idea: str, call: Call = call_claude) -> GenerationResult:
    """Generate one AI recipe, check it like every other recipe, and save it only if it passes."""
    ctx = load_context(session)
    rules = get_exclusion_rules(session)
    titles, slugs = all_titles_and_slugs(session)

    def check(recipe: Recipe, catalogue: dict[str, Ingredient]) -> list[str]:
        result = Context(catalogue, ctx.targets, ctx.settings, ctx.rule_settings).check(recipe, rules)
        return [f"{h} - not allowed" for h in result.exclusions] + [
            str(i) for i in result.issues if i.level == "fail"]

    system = system_prompt(ctx.catalogue, targets_text(ctx.targets, ctx.settings.get("same_lunch_as_dinner", True)),
                           "\n".join(get_exclusion_notes(session)), sorted(titles))
    result = generate_recipe(system, tier, idea, ctx.catalogue, check, titles, slugs, call=call)
    if result.ok:
        for ingredient in result.new_ingredients:
            save_ingredient(session, ingredient)
        session.flush()
        save_recipe(session, result.recipe)
        session.commit()
    return result
