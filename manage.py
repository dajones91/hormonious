"""Command-line helpers. Run from the project folder, e.g.:

    python manage.py reset-db          # rebuild the local database from data/
    python manage.py recipes           # list recipes with per-person dinner plates and rule checks
    python manage.py check "oyster sauce"   # test the exclusion filter on any ingredient name
    python manage.py serve             # run the web app at http://127.0.0.1:5000
    python manage.py serve --lan       # ...and let phones on your Wi-Fi open it too
"""

import argparse

from core.exclusions import check_name
from core.portions import Plate
from db.models import make_session_factory
from db.planner import check_all
from db.repo import get_exclusion_rules, reset_and_seed


def cmd_reset_db(session) -> None:
    counts = reset_and_seed(session)
    print("Database rebuilt: " + ", ".join(f"{n} {what}" for what, n in counts.items()))


def describe(plate: Plate) -> str:
    n = plate.total.rounded()
    carb = next((c for c in plate.components if c.component == "carb"), None)
    carb_text = f" + {carb.grams:.0f} g {carb.weight_label} {carb.ingredient.name.lower()}".replace("  ", " ") \
        if carb else ""
    return f"{n.kcal:>4.0f} kcal {n.protein:>3.0f}P {n.carbs:>3.0f}C {n.fibre:>3.0f}F{carb_text}"


def cmd_recipes(session) -> None:
    checks = check_all(session)
    for c in checks:
        status = "OK  " if c.ok else "FAIL"
        dinner = {p.person: p for p in c.plates if p.meal == "dinner"}
        print(f"{status} {c.recipe.slug} ({c.recipe.tier}, {c.recipe.total_min} min)")
        for person in ("dale", "jade"):
            print(f"       {person.title():<5} dinner: {describe(dinner[person])}")
        for issue in [*c.exclusions, *c.issues]:
            print(f"       - {issue}")
    failing = sum(not c.ok for c in checks)
    print(f"\n{len(checks) - failing} of {len(checks)} recipes can go on the menu. Values are estimates.")


def cmd_check(session, name: str) -> None:
    hits = check_name(name, get_exclusion_rules(session))
    print("\n".join(f"EXCLUDED: {h}" for h in hits) if hits else f"'{name}' is allowed for everyone.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Hormonious helper commands")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("reset-db", help="rebuild the local database from data/")
    sub.add_parser("recipes", help="list recipes with per-person plates and rule checks")
    check = sub.add_parser("check", help="test the exclusion filter on an ingredient name")
    check.add_argument("name")
    serve = sub.add_parser("serve", help="run the web app locally")
    serve.add_argument("--lan", action="store_true",
                       help="let phones on your home Wi-Fi connect (turns the debugger off)")
    args = parser.parse_args()

    if args.command == "serve":
        from app import create_app
        # The debugger can run code, so it's only on when the app is reachable from this PC alone.
        create_app().run(host="0.0.0.0" if args.lan else "127.0.0.1", port=5000, debug=not args.lan)
        return

    with make_session_factory()() as session:
        if args.command == "reset-db":
            cmd_reset_db(session)
        elif args.command == "recipes":
            cmd_recipes(session)
        else:
            cmd_check(session, args.name)


if __name__ == "__main__":
    main()
