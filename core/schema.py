"""The shapes of our data: ingredients and recipes.

Pydantic checks every value when an object is created, so a recipe with a
missing field or a negative weight is rejected straight away. The same models
will later validate AI-generated and imported recipes.
"""

from typing import Literal

from pydantic import BaseModel, Field, model_validator

Tier = Literal["weeknight", "weekend"]
Source = Literal["seed", "ai", "imported"]


class Ingredient(BaseModel):
    """One entry in the ingredient table. Nutrition is per 100 g in `state`."""

    key: str
    name: str
    aisle: str
    state: Literal["raw", "dry", "cooked", "as_sold"]
    kcal: float = Field(ge=0)
    protein: float = Field(ge=0)
    carbs: float = Field(ge=0)
    sugars: float = Field(ge=0)
    fibre: float = Field(ge=0)
    fat: float = Field(ge=0)
    cooked_yield: float = Field(default=1.0, gt=0)  # cooked weight = grams x this
    gi: Literal["low", "medium", "high", "na"] = "na"
    flags: set[str] = set()  # e.g. protein, vegetable, healthy_fat, wholegrain
    families: set[str] = set()  # food families used by exclusions, e.g. salmon
    pack_unit: Literal["g", "each"] = "g"
    packs: list[float] = []  # pack sizes in grams, or counts when pack_unit is "each"
    pack_label: str = "pack"
    unit_g: float | None = None  # grams per item, for things bought individually
    staple: bool = False  # usually in the cupboard already
    source: str = "approx"
    verified: bool = False


class RecipeItem(BaseModel):
    """A shared-base ingredient. `grams` is the total for all servings."""

    ingredient: str
    grams: float = Field(gt=0)
    display: str | None = None  # friendly amount, e.g. "2 tbsp" or "1 x 400 g tin"
    note: str | None = None  # prep, e.g. "cut into chunks"


class FlexOption(BaseModel):
    """One choice for a flexible component. Grams are per person, per meal."""

    ingredient: str
    standard_grams: float = Field(gt=0)
    min_grams: float = Field(default=0, ge=0)
    max_grams: float = Field(gt=0)
    default: bool = False

    @model_validator(mode="after")
    def _check_range(self):
        if not (self.min_grams <= self.standard_grams <= self.max_grams):
            raise ValueError("need min_grams <= standard_grams <= max_grams")
        return self


class FlexComponent(BaseModel):
    """A part of the meal sized per person, e.g. the carb or a cheese topping."""

    component: str
    options: list[FlexOption] = Field(min_length=1)
    cook_note: str | None = None

    @model_validator(mode="after")
    def _one_default(self):
        defaults = [o for o in self.options if o.default]
        if len(defaults) != 1:
            raise ValueError(f"component '{self.component}' needs exactly one default option")
        return self

    @property
    def default_option(self) -> FlexOption:
        return next(o for o in self.options if o.default)


class Recipe(BaseModel):
    slug: str = Field(pattern=r"^[a-z0-9-]+$")
    title: str
    source: Source = "seed"
    source_url: str | None = None
    servings: int = Field(default=4, gt=0)
    active_min: int = Field(gt=0)
    total_min: int = Field(gt=0)
    tier: Tier
    cuisine: str
    spice: int = Field(default=1, ge=0, le=3)  # 0 none ... 3 hot
    tags: list[str] = []
    shared: list[RecipeItem] = Field(min_length=1)
    flexible: list[FlexComponent] = []
    steps: list[str] = Field(min_length=1)
    reheat_note: str | None = None
    base_split: dict[str, float] | None = None  # e.g. {"dale": 0.55, "jade": 0.45}

    @model_validator(mode="after")
    def _check(self):
        if self.active_min > self.total_min:
            raise ValueError("active time can't be longer than total time")
        if self.base_split is not None and abs(sum(self.base_split.values()) - 1) > 0.001:
            raise ValueError("base_split must add up to 1")
        return self

    def ingredient_keys(self) -> set[str]:
        """Every ingredient the recipe could use, including all swap options."""
        keys = {item.ingredient for item in self.shared}
        for comp in self.flexible:
            keys |= {o.ingredient for o in comp.options}
        return keys
