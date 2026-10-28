"""Command-line helpers. Run from the project folder, e.g.:

    python manage.py reset-db          # rebuild the local database from data/
    python manage.py recipes           # list recipes with exclusion + nutrition checks
    python manage.py check "oyster sauce"   # test the exclusion filter on any ingredient name
"""

import argparse

from core.exclusions import check_name, check_recipe, is_vegetarian
from core.nutrition import Nutrition, base_per_portion, for_grams
from core.schema import Ingredient, Recipe
from db.models import make_session_factory
from db.repo import get_catalogue, get_exclusion_rules, get_recipes, reset_and_seed

# Stage 1 sanity check, on an even split with standard flexible portions.
# Proper per-person checks against each profile arrive in stage 2.
MIN_PROTEIN, MIN_FIBRE, MAX_CARBS_LOWEST = 35, 8, 45
TIME_LIMIT = {"weeknight": 45, "weekend": 90}


def plate(recipe: Recipe, catalogue: dict[str, Ingredient], choose) -> Nutrition:
    """One even portion of the base plus one flexible option per component."""
    total = base_per_portion(recipe, catalogue)
    for comp in recipe.flexible:
        option = choose(comp)
        total += for_grams(catalogue[option.ingredient], option.standard_grams)
    return total


def cmd_reset_db(session) -> None:
    counts = reset_and_seed(session)
    print("Database rebuilt: " + ", ".join(f"{n} {what}" for what, n in counts.items()))


def cmd_recipes(session) -> None:
    catalogue, rules = get_catalogue(session), get_exclusion_rules(session)
    problems = 0
    print(f"{'Recipe':<34}{'Tier':<10}{'Mins':>5}{'Base':>6}{'kcal':>6}{'P':>5}{'C':>5}{'Fib':>5}{'Fat':>5}"
          f"{'C-low':>7}  Notes")
    for r in get_recipes(session):
        base = base_per_portion(r, catalogue).rounded()
        std = plate(r, catalogue, lambda c: c.default_option).rounded()
        low = plate(r, catalogue, lambda c: min(
            c.options, key=lambda o: for_grams(catalogue[o.ingredient], o.standard_grams).carbs)).rounded()
        notes = [str(h) for h in check_recipe(r, catalogue, rules)]
        if std.protein < MIN_PROTEIN:
            notes.append(f"protein under {MIN_PROTEIN} g")
        if std.fibre < MIN_FIBRE:
            notes.append(f"fibre under {MIN_FIBRE} g")
        if low.carbs > MAX_CARBS_LOWEST:
            notes.append(f"carbs over {MAX_CARBS_LOWEST} g even with the lowest-carb swap")
        if r.total_min > TIME_LIMIT[r.tier]:
            notes.append(f"over {TIME_LIMIT[r.tier]} min")
        problems += bool(notes)
        if is_vegetarian(r, catalogue):
            notes.insert(0, "vegetarian")
        print(f"{r.slug[:33]:<34}{r.tier:<10}{r.total_min:>5}{base.kcal:>6.0f}{std.kcal:>6.0f}{std.protein:>5.0f}{std.carbs:>5.0f}"
              f"{std.fibre:>5.0f}{std.fat:>5.0f}{low.carbs:>7.0f}  {'; '.join(notes)}")
    print("\nPer even portion with the default carb at standard size (values are estimates).")
    print("Base = kcal of the shared base alone, before any carb or topping.")
    print("C-low = carbs with the lowest-carb swap. " + ("All recipes pass." if not problems
                                                           else f"{problems} recipe(s) need attention."))


def cmd_check(session, name: str) -> None:
    hits = check_name(name, get_exclusion_rules(session))
    print("\n".join(f"EXCLUDED: {h}" for h in hits) if hits else f"'{name}' is allowed for everyone.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Hormonious helper commands")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("reset-db", help="rebuild the local database from data/")
    sub.add_parser("recipes", help="list recipes with exclusion and nutrition checks")
    check = sub.add_parser("check", help="test the exclusion filter on an ingredient name")
    check.add_argument("name")
    args = parser.parse_args()

    with make_session_factory()() as session:
        if args.command == "reset-db":
            cmd_reset_db(session)
        elif args.command == "recipes":
            cmd_recipes(session)
        else:
            cmd_check(session, args.name)


if __name__ == "__main__":
    main()
