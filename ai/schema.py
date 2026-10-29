"""The exact shape we ask the AI to fill in.

These are kept simpler than core/schema.py (no sets or dicts) so the API can
enforce them. `to_recipe` and `to_ingredient` turn an answer into our normal
objects, which then go through all the usual checks.
"""

import re
from typing import Literal

from pydantic import BaseModel, Field

from core.families import classify_name
from core.schema import Ingredient, Recipe
from core.shopping import AISLE_ORDER

Aisle = Literal[tuple(AISLE_ORDER)]  # type: ignore[valid-type]
Flag = Literal["protein", "vegetable", "healthy_fat", "wholegrain", "pulse", "refined_carb", "added_sugar"]


class AiNewIngredient(BaseModel):
    """An ingredient that isn't in our table yet. Nutrition is per 100 g as weighed (raw or dry)."""

    key: str = Field(description="new snake_case key, e.g. 'pak_choi'")
    name: str = Field(description="UK supermarket name, e.g. 'Pak choi'")
    aisle: Aisle
    state: Literal["raw", "dry", "as_sold"]
    kcal: float
    protein: float
    carbs: float
    sugars: float
    fibre: float
    fat: float
    cooked_yield: float = Field(description="cooked weight / weighed weight, 1 if not cooked separately")
    gi: Literal["low", "medium", "high", "na"]
    flags: list[Flag]
    pack_unit: Literal["g", "each"]
    pack_size: float = Field(description="typical Tesco pack size in grams, or a count if pack_unit is 'each'")
    pack_label: str = Field(description="e.g. 'pack', 'bag', 'jar', or the item name if sold loose")
    unit_g: float | None = Field(description="grams per item when bought individually, else null")


class AiItem(BaseModel):
    ingredient: str = Field(description="ingredient key from the table, or a key from new_ingredients")
    grams: float = Field(description="total grams for all 4 portions, weighed raw/dry")
    display: str | None = Field(description="friendly amount, e.g. '2 tbsp', '1 x 400 g tin', or null")
    note: str | None = Field(description="prep, e.g. 'finely chopped', or null")


class AiOption(BaseModel):
    ingredient: str
    standard_grams: float = Field(description="a typical single portion, per person per meal, raw/dry")
    min_grams: float
    max_grams: float
    default: bool


class AiComponent(BaseModel):
    component: Literal["carb", "topping"]
    options: list[AiOption]
    cook_note: str | None


class AiRecipe(BaseModel):
    title: str
    tier: Literal["weeknight", "weekend"]
    cuisine: str
    spice: int = Field(description="0 none, 1 mild, 2 medium, 3 hot")
    active_min: int
    total_min: int
    tags: list[str]
    shared: list[AiItem]
    flexible: list[AiComponent]
    steps: list[str]
    reheat_note: str


class AiAnswer(BaseModel):
    recipe: AiRecipe
    new_ingredients: list[AiNewIngredient]


def slugify(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:70]


def to_ingredient(new: AiNewIngredient) -> Ingredient:
    """A new ingredient from the AI, tagged with food families and marked as an unverified estimate."""
    return Ingredient(
        key=new.key, name=new.name, aisle=new.aisle, state=new.state, kcal=new.kcal, protein=new.protein,
        carbs=new.carbs, sugars=new.sugars, fibre=new.fibre, fat=new.fat, cooked_yield=new.cooked_yield or 1,
        gi=new.gi, flags=set(new.flags), families=classify_name(new.name), pack_unit=new.pack_unit,
        packs=[new.pack_size] if new.pack_size > 0 else [], pack_label=new.pack_label, unit_g=new.unit_g,
        source="ai-estimate", verified=False,
    )


def to_recipe(r: AiRecipe, slug: str) -> Recipe:
    return Recipe(
        slug=slug, title=r.title, source="ai", servings=4, active_min=r.active_min, total_min=r.total_min,
        tier=r.tier, cuisine=r.cuisine, spice=min(max(r.spice, 0), 3), tags=r.tags,
        shared=[i.model_dump() for i in r.shared],
        flexible=[c.model_dump() for c in r.flexible],
        steps=r.steps, reheat_note=r.reheat_note,
    )
