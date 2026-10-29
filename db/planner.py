"""Brings the core rules and the database together for the web pages and commands."""

from dataclasses import dataclass
from datetime import date

from sqlalchemy.orm import Session

from core.exclusions import ExclusionHit, check_recipe
from core.menu import Menu, build_menu, menu_is_ready, week_slots
from core.portions import Plate, Targets, base_shares, meals_for_portions, plan_plates
from core.rules import Issue, RuleSettings, passes, validate
from core.schema import Ingredient, Recipe
from core.shopping import PlannedCook, ShoppingItem, build_list
from db.models import PlanSlotRow, WeekRow
from db.repo import (create_week, get_catalogue, get_choices, get_exclusion_rules, get_pantry, get_recipe,
                     get_recipes, get_settings, get_targets, get_week, last_cooked)


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

    def plates(self, recipe: Recipe, portions: int = 4, choices=None) -> list[Plate]:
        shares = base_shares(recipe, self.settings["split_mode"], self.settings["fixed_split"], self.targets)
        return plan_plates(recipe, self.catalogue, self.targets, shares, meals_for_portions(portions), choices,
                           same_lunch=self.settings.get("same_lunch_as_dinner", True))

    def check(self, recipe: Recipe, rules, portions: int = 4, choices=None) -> RecipeCheck:
        plates = self.plates(recipe, portions, choices)
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


def make_menu(session: Session, start: date) -> Menu:
    ctx = load_context(session)
    eligible = [c.recipe for c in check_all(session, ctx) if c.ok]
    return build_menu(eligible, start, last_cooked(session, start),
                      ctx.settings["weeknight_options"], ctx.settings["weekend_options"])


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
            plates = ctx.plates(recipe, slot.portions, get_choices(slot))
            cooks.append((slot, PlannedCook(recipe, slot.portions, plates)))
    return cooks


def shopping_list(session: Session, week: WeekRow) -> list[ShoppingItem]:
    ctx = load_context(session)
    cooks = [cook for _, cook in week_cooks(session, week, ctx)]
    return build_list(cooks, ctx.catalogue, get_pantry(session))
