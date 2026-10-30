"""Command-line helpers. Run from the project folder, e.g.:

    python manage.py reset-db          # rebuild the local database from data/
    python manage.py recipes           # list recipes with per-person dinner plates and rule checks
    python manage.py check "oyster sauce"   # test the exclusion filter on any ingredient name
    python manage.py serve             # run the web app at http://127.0.0.1:5000
    python manage.py serve --lan       # ...and let phones on your Wi-Fi open it too
    python manage.py generate --tier weeknight --idea "a lamb curry"   # create an AI recipe (costs ~10-30p)
    python manage.py make-secret       # print a strong random SECRET_KEY to paste into .env
    python manage.py backup            # save a dated copy of the database in backups/
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


def cmd_generate(session, tier: str, idea: str) -> None:
    from ai.generate import AiError
    from db.planner import generate_and_save
    print("Asking the AI for a recipe and checking it... (usually a minute or two)")
    try:
        result = generate_and_save(session, tier, idea)
    except AiError as e:
        print(f"Couldn't generate: {e}")
        return
    for n, problems in enumerate(result.problems, 1):
        print(f"Attempt {n} rejected:\n  - " + "\n  - ".join(problems))
    cost = f"${result.cost_usd:.2f} ({result.input_tokens} input + {result.output_tokens} output tokens)"
    if result.ok:
        print(f"Saved '{result.recipe.title}' ({result.recipe.slug}) after {result.attempts} attempt(s). Cost {cost}.")
        for ing in result.new_ingredients:
            print(f"  New ingredient (AI nutrition estimate, unverified): {ing.name}")
    else:
        print(f"Nothing saved: no attempt passed. Cost {cost}.")


def cmd_backup() -> None:
    """A safe copy of the live database (SQLite's own backup, fine while the app is running)."""
    import sqlite3
    from datetime import datetime
    from db.models import PROJECT_DIR, database_url
    url = database_url()
    if not url.startswith("sqlite:///"):
        print("Backups here only work for the SQLite database.")
        return
    source = url.removeprefix("sqlite:///")
    target = PROJECT_DIR / "backups" / f"hormonious-{datetime.now():%Y-%m-%d-%H%M}.db"
    target.parent.mkdir(exist_ok=True)
    with sqlite3.connect(source) as src, sqlite3.connect(target) as dst:
        src.backup(dst)
    print(f"Backed up to {target}")


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
    gen = sub.add_parser("generate", help="create a new recipe with AI (uses the Anthropic API)")
    gen.add_argument("--tier", choices=["weeknight", "weekend"], default="weeknight")
    gen.add_argument("--idea", default="", help='optional, e.g. "a lamb curry"')
    sub.add_parser("make-secret", help="print a strong random SECRET_KEY for .env")
    sub.add_parser("backup", help="save a dated copy of the database in backups/")
    serve = sub.add_parser("serve", help="run the web app locally")
    serve.add_argument("--lan", action="store_true",
                       help="let phones on your home Wi-Fi connect (turns the debugger off)")
    args = parser.parse_args()

    if args.command == "make-secret":
        import secrets
        print(secrets.token_hex(32))
        return
    if args.command == "backup":
        cmd_backup()
        return
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
        elif args.command == "generate":
            cmd_generate(session, args.tier, args.idea)
        else:
            cmd_check(session, args.name)


if __name__ == "__main__":
    main()
