"""Save core objects to the database and read them back."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from core.exclusions import ExclusionRule
from core.loaders import load_household, load_ingredients, load_recipes
from core.schema import FlexComponent, FlexOption, Ingredient, Recipe, RecipeItem
from db.models import (Base, Exclusion, FlexComponentRow, FlexOptionRow, IngredientRow, Person,
                       RecipeItemRow, RecipeRow)

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


def reset_and_seed(session: Session) -> dict[str, int]:
    """Wipe the database and load everything from data/. For development only."""
    engine = session.get_bind()
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)

    catalogue = load_ingredients()
    for ing in catalogue.values():
        save_ingredient(session, ing)

    household = load_household()
    people = {p["key"]: Person(key=p["key"], name=p["name"]) for p in household["people"]}
    session.add_all(people.values())
    for rule in household["exclusions"]:
        people[rule["person"]].exclusions.append(
            Exclusion(family=rule["family"], exceptions=rule.get("exceptions", []), note=rule.get("note")))

    recipes = load_recipes()
    for recipe in recipes:
        save_recipe(session, recipe)
    session.commit()
    return {"ingredients": len(catalogue), "people": len(people), "recipes": len(recipes)}
