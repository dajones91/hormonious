"""Read the seed data files in data/ into core objects."""

import csv
import json
from pathlib import Path

from core.exclusions import ExclusionRule
from core.schema import Ingredient, Recipe

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def _split(value: str) -> list[str]:
    return [part.strip() for part in value.split(";") if part.strip()]


def load_ingredients(path: Path = DATA_DIR / "ingredients.csv") -> dict[str, Ingredient]:
    catalogue: dict[str, Ingredient] = {}
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            ingredient = Ingredient(
                **{k: row[k] for k in ("key", "name", "aisle", "state", "gi", "pack_unit", "pack_label", "source")},
                **{k: float(row[k]) for k in ("kcal", "protein", "carbs", "sugars", "fibre", "fat", "cooked_yield")},
                flags=set(_split(row["flags"])),
                families=set(_split(row["families"])),
                packs=[float(p) for p in _split(row["packs"])],
                unit_g=float(row["unit_g"]) if row["unit_g"] else None,
                staple=row["staple"] == "1",
                verified=row["verified"] == "1",
            )
            if ingredient.key in catalogue:
                raise ValueError(f"duplicate ingredient key: {ingredient.key}")
            catalogue[ingredient.key] = ingredient
    return catalogue


def load_recipes(path: Path = DATA_DIR / "seed_recipes.json") -> list[Recipe]:
    return [Recipe(**raw) for raw in json.loads(path.read_text(encoding="utf-8"))]


def load_household(path: Path = DATA_DIR / "household.json") -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def exclusion_rules(household: dict) -> list[ExclusionRule]:
    return [
        ExclusionRule(r["person"], r["family"], frozenset(r.get("exceptions", [])))
        for r in household["exclusions"]
    ]
