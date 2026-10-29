"""Database tables. Each class is one table; each attribute is one column.

Lists and sets (tags, steps, families) are stored as JSON columns to keep
the number of tables small.
"""

import os
from datetime import date, datetime

from dotenv import load_dotenv
from sqlalchemy import JSON, ForeignKey, String, UniqueConstraint, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, sessionmaker


class Base(DeclarativeBase):
    pass


class Person(Base):
    __tablename__ = "person"
    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(20), unique=True)
    name: Mapped[str]
    exclusions: Mapped[list["Exclusion"]] = relationship(back_populates="person", cascade="all, delete-orphan")


class Exclusion(Base):
    __tablename__ = "exclusion"
    id: Mapped[int] = mapped_column(primary_key=True)
    person_id: Mapped[int] = mapped_column(ForeignKey("person.id"))
    family: Mapped[str]
    exceptions: Mapped[list[str]] = mapped_column(JSON, default=list)
    note: Mapped[str | None]
    person: Mapped[Person] = relationship(back_populates="exclusions")


class IngredientRow(Base):
    __tablename__ = "ingredient"
    key: Mapped[str] = mapped_column(String(60), primary_key=True)
    name: Mapped[str]
    aisle: Mapped[str]
    state: Mapped[str]
    kcal: Mapped[float]
    protein: Mapped[float]
    carbs: Mapped[float]
    sugars: Mapped[float]
    fibre: Mapped[float]
    fat: Mapped[float]
    cooked_yield: Mapped[float]
    gi: Mapped[str]
    flags: Mapped[list[str]] = mapped_column(JSON, default=list)
    families: Mapped[list[str]] = mapped_column(JSON, default=list)
    pack_unit: Mapped[str]
    packs: Mapped[list[float]] = mapped_column(JSON, default=list)
    pack_label: Mapped[str]
    unit_g: Mapped[float | None]
    staple: Mapped[bool]
    source: Mapped[str]
    verified: Mapped[bool]


class RecipeRow(Base):
    __tablename__ = "recipe"
    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(80), unique=True)
    title: Mapped[str]
    source: Mapped[str]
    source_url: Mapped[str | None]
    servings: Mapped[int]
    active_min: Mapped[int]
    total_min: Mapped[int]
    tier: Mapped[str]
    cuisine: Mapped[str]
    spice: Mapped[int]
    tags: Mapped[list[str]] = mapped_column(JSON, default=list)
    steps: Mapped[list[str]] = mapped_column(JSON, default=list)
    reheat_note: Mapped[str | None]
    base_split: Mapped[dict | None] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(default="active")  # active / retired
    created_at: Mapped[datetime] = mapped_column(default=datetime.now)
    items: Mapped[list["RecipeItemRow"]] = relationship(
        back_populates="recipe", cascade="all, delete-orphan", order_by="RecipeItemRow.position")
    components: Mapped[list["FlexComponentRow"]] = relationship(
        back_populates="recipe", cascade="all, delete-orphan", order_by="FlexComponentRow.position")


class RecipeItemRow(Base):
    """A shared-base ingredient line."""

    __tablename__ = "recipe_item"
    id: Mapped[int] = mapped_column(primary_key=True)
    recipe_id: Mapped[int] = mapped_column(ForeignKey("recipe.id"))
    position: Mapped[int]
    ingredient_key: Mapped[str] = mapped_column(ForeignKey("ingredient.key"))
    grams: Mapped[float]
    display: Mapped[str | None]
    note: Mapped[str | None]
    recipe: Mapped[RecipeRow] = relationship(back_populates="items")


class FlexComponentRow(Base):
    __tablename__ = "flex_component"
    id: Mapped[int] = mapped_column(primary_key=True)
    recipe_id: Mapped[int] = mapped_column(ForeignKey("recipe.id"))
    position: Mapped[int]
    component: Mapped[str]
    cook_note: Mapped[str | None]
    recipe: Mapped[RecipeRow] = relationship(back_populates="components")
    options: Mapped[list["FlexOptionRow"]] = relationship(
        back_populates="component_row", cascade="all, delete-orphan", order_by="FlexOptionRow.position")


class FlexOptionRow(Base):
    __tablename__ = "flex_option"
    id: Mapped[int] = mapped_column(primary_key=True)
    component_id: Mapped[int] = mapped_column(ForeignKey("flex_component.id"))
    position: Mapped[int]
    ingredient_key: Mapped[str] = mapped_column(ForeignKey("ingredient.key"))
    standard_grams: Mapped[float]
    min_grams: Mapped[float]
    max_grams: Mapped[float]
    is_default: Mapped[bool]
    component_row: Mapped[FlexComponentRow] = relationship(back_populates="options")


class TargetRow(Base):
    """Per-person, per-meal nutrition targets (editable on the Profiles page)."""

    __tablename__ = "target"
    __table_args__ = (UniqueConstraint("person_id", "meal"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    person_id: Mapped[int] = mapped_column(ForeignKey("person.id"))
    meal: Mapped[str]  # dinner / lunch
    kcal: Mapped[float]
    protein_min: Mapped[float]
    carbs_target: Mapped[float]
    carbs_max: Mapped[float | None]
    fibre_min: Mapped[float]
    person: Mapped[Person] = relationship()


class SettingRow(Base):
    __tablename__ = "setting"
    key: Mapped[str] = mapped_column(String(60), primary_key=True)
    value: Mapped[object] = mapped_column(JSON)


class WeekRow(Base):
    """A planning week (Saturday to Friday) and the menu offered for it."""

    __tablename__ = "week"
    id: Mapped[int] = mapped_column(primary_key=True)
    start: Mapped[date] = mapped_column(unique=True)
    weeknight_options: Mapped[list[str]] = mapped_column(JSON, default=list)
    weekend_options: Mapped[list[str]] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(default=datetime.now)
    slots: Mapped[list["PlanSlotRow"]] = relationship(
        back_populates="week", cascade="all, delete-orphan", order_by="PlanSlotRow.day")


class PlanSlotRow(Base):
    """What we're doing on one day: a recipe, or a no-cook night."""

    __tablename__ = "plan_slot"
    __table_args__ = (UniqueConstraint("week_id", "day"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    week_id: Mapped[int] = mapped_column(ForeignKey("week.id"))
    day: Mapped[date]
    recipe_slug: Mapped[str | None] = mapped_column(ForeignKey("recipe.slug"))
    no_cook: Mapped[bool] = mapped_column(default=False)
    portions: Mapped[int]
    week: Mapped[WeekRow] = relationship(back_populates="slots")
    choices: Mapped[list["PortionChoiceRow"]] = relationship(cascade="all, delete-orphan")


class PortionChoiceRow(Base):
    """Someone's change to their flexible portion for one planned night."""

    __tablename__ = "portion_choice"
    __table_args__ = (UniqueConstraint("slot_id", "person", "meal", "component"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    slot_id: Mapped[int] = mapped_column(ForeignKey("plan_slot.id"))
    person: Mapped[str]
    meal: Mapped[str]
    component: Mapped[str]
    option: Mapped[str | None]  # ingredient key; None = the default option
    grams: Mapped[float | None]  # None = sized automatically


class PantryRow(Base):
    """Ingredients we always have in, hidden from the shopping list by default."""

    __tablename__ = "pantry"
    ingredient_key: Mapped[str] = mapped_column(ForeignKey("ingredient.key"), primary_key=True)


class ShoppingTickRow(Base):
    __tablename__ = "shopping_tick"
    __table_args__ = (UniqueConstraint("week_id", "ingredient_key"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    week_id: Mapped[int] = mapped_column(ForeignKey("week.id"))
    ingredient_key: Mapped[str] = mapped_column(ForeignKey("ingredient.key"))


class RatingRow(Base):
    """One person's rating of a recipe after cooking it (on a particular night, if known)."""

    __tablename__ = "rating"
    id: Mapped[int] = mapped_column(primary_key=True)
    recipe_slug: Mapped[str] = mapped_column(ForeignKey("recipe.slug"))
    slot_id: Mapped[int | None] = mapped_column(ForeignKey("plan_slot.id"))
    person: Mapped[str]
    stars: Mapped[int]
    note: Mapped[str] = mapped_column(default="")
    rated_on: Mapped[date]


class RecipeRestoreRow(Base):
    """A recipe we brought back after rating it 2 stars or less; earlier ratings are ignored."""

    __tablename__ = "recipe_restore"
    recipe_slug: Mapped[str] = mapped_column(ForeignKey("recipe.slug"), primary_key=True)
    restored_on: Mapped[date]


def make_session_factory(url: str | None = None) -> sessionmaker:
    """Connect to the database named in .env (DATABASE_URL), or the URL given."""
    load_dotenv()
    url = url or os.getenv("DATABASE_URL", "sqlite:///hormonious.db")
    engine = create_engine(url)
    Base.metadata.create_all(engine)  # adds any brand-new tables; never changes existing ones
    return sessionmaker(engine)
