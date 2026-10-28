"""Web pages: the week plan, the recipe library, a recipe, and profiles."""

from datetime import date, timedelta

from flask import Blueprint, abort, current_app, flash, g, redirect, render_template, request, url_for

from core.menu import check_assignment, menu_ready_date, week_slots, week_start_for
from core.portions import MEALS, PEOPLE, MealTarget
from db.planner import check_all, ensure_week, load_context
from db.repo import get_exclusion_rules, get_recipe, get_recipes, save_target, set_setting, set_slot

bp = Blueprint("main", __name__)


def db():
    if "db" not in g:
        g.db = current_app.config["SESSION_FACTORY"]()
    return g.db


def today() -> date:
    return current_app.config["TODAY"] or date.today()


@bp.route("/")
def home():
    return redirect(url_for("main.week"))


@bp.route("/week", methods=["GET"])
@bp.route("/week/<start>", methods=["GET", "POST"])
def week(start: str | None = None):
    week_start = date.fromisoformat(start) if start else week_start_for(today())
    if week_start.weekday() != 5:
        abort(404)
    session = db()
    week_row = ensure_week(session, week_start)
    recipes = {r.slug: r for r in get_recipes(session)}
    slots = week_slots(week_start, load_context(session).settings["friday_plan"])

    if request.method == "POST":
        chosen = {}
        for slot in slots:
            value = request.form.get(f"slot-{slot.day.isoformat()}", "")
            if slot.kind == "off" and value != "":
                continue
            chosen[slot.day] = value
        picked = [v for v in chosen.values() if v not in ("", "no-cook")]
        if len(picked) != len(set(picked)) or any(v not in recipes for v in picked):
            flash("Each recipe can only go on one night a week.", "error")
            return redirect(url_for("main.week", start=week_start.isoformat()))
        for day, value in chosen.items():
            recipe_slug = None if value in ("", "no-cook") else value
            set_slot(session, week_row, day, recipe_slug, no_cook=value == "no-cook")
        session.commit()
        flash("Plan saved.", "ok")
        return redirect(url_for("main.week", start=week_start.isoformat()))

    rows = []
    stored = {s.day: s for s in week_row.slots}
    for slot in slots:
        saved = stored.get(slot.day)
        recipe = recipes.get(saved.recipe_slug) if saved and saved.recipe_slug else None
        rows.append({
            "slot": slot,
            "value": "no-cook" if saved and saved.no_cook else (recipe.slug if recipe else ""),
            "recipe": recipe,
            "warnings": check_assignment(slot, recipe) if recipe else [],
        })
    return render_template(
        "week.html", week_start=week_start, rows=rows, recipes=recipes,
        weeknight=[recipes[s] for s in week_row.weeknight_options if s in recipes],
        weekend=[recipes[s] for s in week_row.weekend_options if s in recipes],
        cooking=sum(1 for r in rows if r["recipe"]),
        ready=menu_ready_date(week_start), today=today(),
        prev_week=(week_start - timedelta(days=7)).isoformat(), next_week=(week_start + timedelta(days=7)).isoformat(),
    )


@bp.route("/recipes")
def recipes():
    return render_template("recipes.html", checks=check_all(db()))


@bp.route("/recipe/<slug>")
def recipe(slug: str):
    session = db()
    r = get_recipe(session, slug)
    if r is None:
        abort(404)
    ctx = load_context(session)
    check = ctx.check(r, get_exclusion_rules(session))
    return render_template("recipe.html", r=r, check=check, catalogue=ctx.catalogue, targets=ctx.targets)


@bp.route("/profiles", methods=["GET", "POST"])
def profiles():
    session = db()
    ctx = load_context(session)
    if request.method == "POST":
        try:
            for person in PEOPLE:
                for meal in MEALS:
                    f = lambda name: request.form.get(f"{person}-{meal}-{name}", "").strip()
                    carbs_max = f("carbs_max")
                    save_target(session, person, meal, MealTarget(
                        kcal=float(f("kcal")), protein_min=float(f("protein_min")),
                        carbs_target=float(f("carbs_target")), carbs_max=float(carbs_max) if carbs_max else None,
                        fibre_min=float(f("fibre_min"))))
            mode = request.form.get("split_mode", "even")
            if mode not in ("even", "protein", "fixed"):
                raise ValueError("unknown split mode")
            set_setting(session, "split_mode", mode)
            dale = float(request.form.get("fixed_dale", 55)) / 100
            if not 0 < dale < 1:
                raise ValueError("Dale's share must be between 1 and 99%")
            set_setting(session, "fixed_split", {"dale": round(dale, 3), "jade": round(1 - dale, 3)})
        except ValueError as e:
            session.rollback()
            flash(f"Not saved: please check the numbers ({e}).", "error")
            return redirect(url_for("main.profiles"))
        session.commit()
        flash("Profiles saved. Menus built from now on use the new targets.", "ok")
        return redirect(url_for("main.profiles"))
    return render_template("profiles.html", targets=ctx.targets, settings=ctx.settings, people=PEOPLE, meals=MEALS)
