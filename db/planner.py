"""Brings the core rules and the database together for the web pages and commands."""

from dataclasses import dataclass
from datetime import date

from sqlalchemy.orm import Session

from core.exclusions import ExclusionHit, check_recipe
from core.menu import build_menu, week_slots
from core.portions import Plate, Targets, base_shares, plan_plates
from core.rules import Issue, RuleSettings, passes, validate
from core.schema import Ingredient, Recipe
from db.models import WeekRow
from db.repo import (create_week, get_catalogue, get_exclusion_rules, get_recipes, get_settings, get_targets,
                     get_week, last_cooked)


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

    def check(self, recipe: Recipe, rules) -> RecipeCheck:
        shares = base_shares(recipe, self.settings["split_mode"], self.settings["fixed_split"], self.targets)
        plates = plan_plates(recipe, self.catalogue, self.targets, shares)
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


def ensure_week(session: Session, start: date) -> WeekRow:
    """Get the week's menu and plan, building the menu the first time it's asked for."""
    week = get_week(session, start)
    if week is None:
        ctx = load_context(session)
        eligible = [c.recipe for c in check_all(session, ctx) if c.ok]
        menu = build_menu(eligible, start, last_cooked(session, start),
                          ctx.settings["weeknight_options"], ctx.settings["weekend_options"])
        week = create_week(session, start, menu, week_slots(start, ctx.settings["friday_plan"]))
        session.commit()
    return week
