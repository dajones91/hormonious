"""Save core objects to the database and read them back."""

from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from core.exclusions import ExclusionRule
from core.loaders import load_household, load_ingredients, load_recipes
from core.menu import DaySlot, Menu
from core.portions import Eaters, FlexChoice, MealTarget, Targets, all_eaters, meals_for_portions
from core.ratings import Rating
from core.schema import FlexComponent, FlexOption, Ingredient, Recipe, RecipeItem
from db.models import (Base, Exclusion, FlexComponentRow, FlexOptionRow, IngredientRow, PantryRow, Person,
                       PlanSlotRow, PortionChoiceRow, RatingRow, RecipeItemRow, RecipeRestoreRow, RecipeRow,
                       SettingRow, ShoppingTickRow, SlotEatersRow, TargetRow, WeekRow)

_RECIPE_FIELDS = ("slug", "title", "source", "source_url", "servings", "active_min", "total_min",
                  "tier", "cuisine", "spice", "tags", "steps", "reheat_note", "base_split")


def save_ingredient(session: Session, ing: Ingredient) -> None:
    data = ing.model_dump()
    data["flags"] = sorted(data["flags"])
    data["families"] = sorted(data["families"])
    session.merge(IngredientRow(**data))


def save_recipe(session: Session, recipe: Recipe) -> RecipeRow:
    row = RecipeRow(**{f: getattr(recipe, f) for f in _RECIPE_FIELDS})
    row.items = [
        RecipeItemRow(position=i, ingredient_key=it.ingredient, grams=it.grams, display=it.display, note=it.note)
        for i, it in enumerate(recipe.shared)
    ]
    row.components = [
        FlexComponentRow(position=i, component=c.component, cook_note=c.cook_note, options=[
            FlexOptionRow(position=j, ingredient_key=o.ingredient, standard_grams=o.standard_grams,
                          min_grams=o.min_grams, max_grams=o.max_grams, is_default=o.default)
            for j, o in enumerate(c.options)
        ])
        for i, c in enumerate(recipe.flexible)
    ]
    session.add(row)
    return row


def to_recipe(row: RecipeRow) -> Recipe:
    return Recipe(
        **{f: getattr(row, f) for f in _RECIPE_FIELDS},
        shared=[RecipeItem(ingredient=it.ingredient_key, grams=it.grams, display=it.display, note=it.note)
                for it in row.items],
        flexible=[FlexComponent(component=c.component, cook_note=c.cook_note, options=[
            FlexOption(ingredient=o.ingredient_key, standard_grams=o.standard_grams, min_grams=o.min_grams,
                       max_grams=o.max_grams, default=o.is_default)
            for o in c.options
        ]) for c in row.components],
    )


def get_catalogue(session: Session) -> dict[str, Ingredient]:
    rows = session.scalars(select(IngredientRow)).all()
    return {r.key: Ingredient(**{c.key: getattr(r, c.key) for c in IngredientRow.__table__.columns}) for r in rows}


def get_recipes(session: Session, status: str = "active") -> list[Recipe]:
    rows = session.scalars(select(RecipeRow).where(RecipeRow.status == status).order_by(RecipeRow.id)).all()
    return [to_recipe(r) for r in rows]


def get_exclusion_rules(session: Session) -> list[ExclusionRule]:
    rows = session.scalars(select(Exclusion)).all()
    return [ExclusionRule(r.person.key, r.family, frozenset(r.exceptions)) for r in rows]


def get_recipe(session: Session, slug: str) -> Recipe | None:
    row = session.scalar(select(RecipeRow).where(RecipeRow.slug == slug))
    return to_recipe(row) if row else None


def get_targets(session: Session) -> Targets:
    targets: Targets = {}
    for row in session.scalars(select(TargetRow)).all():
        targets.setdefault(row.person.key, {})[row.meal] = MealTarget(
            row.kcal, row.protein_min, row.carbs_target, row.carbs_max, row.fibre_min)
    return targets


def save_target(session: Session, person: str, meal: str, target: MealTarget) -> None:
    row = session.scalar(select(TargetRow).join(Person).where(Person.key == person, TargetRow.meal == meal))
    for field in ("kcal", "protein_min", "carbs_target", "carbs_max", "fibre_min"):
        setattr(row, field, getattr(target, field))


def get_settings(session: Session) -> dict:
    return {row.key: row.value for row in session.scalars(select(SettingRow)).all()}


def set_setting(session: Session, key: str, value) -> None:
    session.merge(SettingRow(key=key, value=value))


def last_cooked(session: Session, before: date) -> dict[str, date]:
    """The most recent planned day for each recipe, before the given date."""
    rows = session.execute(
        select(PlanSlotRow.recipe_slug, func.max(PlanSlotRow.day))
        .where(PlanSlotRow.recipe_slug.is_not(None), PlanSlotRow.day < before)
        .group_by(PlanSlotRow.recipe_slug)).all()
    return dict(rows)


def get_week(session: Session, start: date) -> WeekRow | None:
    return session.scalar(select(WeekRow).where(WeekRow.start == start))


def create_week(session: Session, start: date, menu: Menu, slots: list[DaySlot]) -> WeekRow:
    week = WeekRow(start=start, weeknight_options=menu.weeknight, weekend_options=menu.weekend)
    week.slots = [PlanSlotRow(day=s.day, portions=s.portions) for s in slots]
    session.add(week)
    session.flush()
    return week


def set_slot(session: Session, week: WeekRow, day: date, recipe_slug: str | None, no_cook: bool) -> None:
    slot = next(s for s in week.slots if s.day == day)
    new_slug = None if no_cook else recipe_slug
    if slot.recipe_slug != new_slug:
        slot.choices.clear()  # portion changes belong to the old recipe
    slot.recipe_slug = new_slug
    slot.no_cook = no_cook


def get_slot(session: Session, slot_id: int) -> PlanSlotRow | None:
    return session.get(PlanSlotRow, slot_id)


def get_choices(slot: PlanSlotRow) -> dict[tuple[str, str], dict[str, FlexChoice]]:
    choices: dict[tuple[str, str], dict[str, FlexChoice]] = {}
    for c in slot.choices:
        choices.setdefault((c.person, c.meal), {})[c.component] = FlexChoice(c.option, c.grams)
    return choices


def save_choice(slot: PlanSlotRow, person: str, meal: str, component: str,
                option: str | None, grams: float | None) -> None:
    """Store a change, or remove it when it's back to automatic."""
    existing = next((c for c in slot.choices
                     if (c.person, c.meal, c.component) == (person, meal, component)), None)
    if option is None and grams is None:
        if existing:
            slot.choices.remove(existing)
    elif existing:
        existing.option, existing.grams = option, grams
    else:
        slot.choices.append(PortionChoiceRow(person=person, meal=meal, component=component,
                                             option=option, grams=grams))


def get_pantry(session: Session) -> set[str]:
    return set(session.scalars(select(PantryRow.ingredient_key)).all())


def toggle_pantry(session: Session, key: str) -> bool:
    """Add to or remove from the pantry. Returns True if it's now in the pantry."""
    row = session.get(PantryRow, key)
    if row:
        session.delete(row)
        return False
    session.add(PantryRow(ingredient_key=key))
    return True


def get_ticks(session: Session, week: WeekRow) -> set[str]:
    return set(session.scalars(select(ShoppingTickRow.ingredient_key).where(ShoppingTickRow.week_id == week.id)))


def toggle_tick(session: Session, week: WeekRow, key: str) -> bool:
    """Tick or untick an item. Returns True if it's now ticked."""
    row = session.scalar(select(ShoppingTickRow).where(ShoppingTickRow.week_id == week.id,
                                                       ShoppingTickRow.ingredient_key == key))
    if row:
        session.delete(row)
        return False
    session.add(ShoppingTickRow(week_id=week.id, ingredient_key=key))
    return True


def reset_and_seed(session: Session) -> dict[str, int]:
    """Wipe the database and load everything from data/. For development only."""
    engine = session.get_bind()
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)

    catalogue = load_ingredients()
    for ing in catalogue.values():
        save_ingredient(session, ing)
    session.flush()
    session.add_all(PantryRow(ingredient_key=k) for k, ing in catalogue.items() if ing.staple)

    household = load_household()
    people = {p["key"]: Person(key=p["key"], name=p["name"]) for p in household["people"]}
    session.add_all(people.values())
    for rule in household["exclusions"]:
        people[rule["person"]].exclusions.append(
            Exclusion(family=rule["family"], exceptions=rule.get("exceptions", []), note=rule.get("note")))

    for person_key, meals in household["targets"].items():
        for meal, t in meals.items():
            session.add(TargetRow(person=people[person_key], meal=meal, **t))
    for key, value in household["settings"].items():
        session.add(SettingRow(key=key, value=value))

    recipes = load_recipes()
    for recipe in recipes:
        save_recipe(session, recipe)
    session.commit()
    return {"ingredients": len(catalogue), "people": len(people), "recipes": len(recipes)}


def add_rating(session: Session, recipe_slug: str, person: str, stars: int, note: str, on: date,
               slot_id: int | None = None) -> None:
    """Record a rating. Re-rating the same night replaces that person's earlier rating for it."""
    if slot_id is not None:
        existing = session.scalar(select(RatingRow).where(RatingRow.slot_id == slot_id, RatingRow.person == person))
        if existing:
            existing.stars, existing.note, existing.rated_on = stars, note, on
            return
    session.add(RatingRow(recipe_slug=recipe_slug, slot_id=slot_id, person=person, stars=stars, note=note,
                          rated_on=on))


def get_ratings(session: Session, recipe_slug: str | None = None) -> dict[str, list[Rating]]:
    """Ratings per recipe, oldest first."""
    query = select(RatingRow).order_by(RatingRow.rated_on, RatingRow.id)
    if recipe_slug:
        query = query.where(RatingRow.recipe_slug == recipe_slug)
    ratings: dict[str, list[Rating]] = {}
    for row in session.scalars(query):
        ratings.setdefault(row.recipe_slug, []).append(Rating(row.person, row.stars, row.rated_on, row.note))
    return ratings


def get_slot_ratings(session: Session, slot_id: int) -> dict[str, RatingRow]:
    return {r.person: r for r in session.scalars(select(RatingRow).where(RatingRow.slot_id == slot_id))}


def get_restores(session: Session) -> dict[str, date]:
    return {r.recipe_slug: r.restored_on for r in session.scalars(select(RecipeRestoreRow))}


def restore_recipe(session: Session, recipe_slug: str, on: date) -> None:
    session.merge(RecipeRestoreRow(recipe_slug=recipe_slug, restored_on=on))


def all_titles_and_slugs(session: Session) -> tuple[set[str], set[str]]:
    """Every recipe's title and slug, whatever its status (so the AI never repeats a removed one)."""
    rows = session.execute(select(RecipeRow.title, RecipeRow.slug)).all()
    return {t for t, _ in rows}, {s for _, s in rows}


def get_recipe_source_and_status(session: Session, slug: str) -> tuple[str, str] | None:
    row = session.scalar(select(RecipeRow).where(RecipeRow.slug == slug))
    return (row.source, row.status) if row else None


def set_recipe_status(session: Session, slug: str, status: str) -> None:
    row = session.scalar(select(RecipeRow).where(RecipeRow.slug == slug))
    row.status = status


def get_exclusion_notes(session: Session) -> list[str]:
    return [f"- {r.person.name}: {r.note or r.family}" for r in session.scalars(select(Exclusion))]


def default_eaters(slot: PlanSlotRow) -> Eaters:
    """Both of us, for dinner and, on 4-portion nights, the next day's lunch."""
    return all_eaters(meals_for_portions(slot.portions))


def get_eaters(session: Session, slot: PlanSlotRow) -> Eaters:
    row = session.get(SlotEatersRow, slot.id)
    if row is None:
        return default_eaters(slot)
    return {tuple(e.split(":", 1)) for e in row.eaters}


def set_eaters(session: Session, slot: PlanSlotRow, eaters: Eaters) -> None:
    """Store who's eating; going back to the default removes the stored row."""
    row = session.get(SlotEatersRow, slot.id)
    if eaters == default_eaters(slot):
        if row:
            session.delete(row)
        return
    value = sorted(f"{p}:{m}" for p, m in eaters)
    if row:
        row.eaters = value
    else:
        session.add(SlotEatersRow(slot_id=slot.id, eaters=value))
