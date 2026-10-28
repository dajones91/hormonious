"""Web pages: the week plan, recipe cards, the shopping list, the library and profiles."""

from datetime import date, timedelta

from flask import Blueprint, Response, abort, current_app, flash, g, redirect, render_template, request, url_for

from core.cooking import cook_base, cook_flex, pot_shares
from core.menu import check_assignment, menu_ready_date, week_slots, week_start_for
from core.portions import MEALS, PEOPLE, MealTarget, meals_for_portions
from core.shopping import as_text, group_by_aisle
from db.planner import check_all, ensure_week, load_context, shopping_list
from db.repo import (get_choices, get_exclusion_rules, get_recipe, get_recipes, get_slot, get_ticks, save_choice,
                     save_target, set_setting, set_slot, toggle_pantry, toggle_tick)

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
            "slot_id": saved.id if saved else None,
            "warnings": check_assignment(slot, recipe) if recipe else [],
        })
    on_menu = set(week_row.weeknight_options) | set(week_row.weekend_options)
    return render_template(
        "week.html", week_start=week_start, rows=rows, recipes=recipes,
        weeknight=[recipes[s] for s in week_row.weeknight_options if s in recipes],
        weekend=[recipes[s] for s in week_row.weekend_options if s in recipes],
        others=sorted((r for s, r in recipes.items() if s not in on_menu), key=lambda r: r.title),
        cooking=sum(1 for r in rows if r["recipe"]),
        ready=menu_ready_date(week_start), today=today(),
        prev_week=(week_start - timedelta(days=7)).isoformat(), next_week=(week_start + timedelta(days=7)).isoformat(),
    )


@bp.route("/recipes")
def recipes():
    return render_template("recipes.html", checks=check_all(db()))


def card_context(ctx, recipe, check, portions: int) -> dict:
    """Everything the recipe card template needs."""
    plates = check.plates
    return dict(
        r=recipe, check=check, portions=portions, targets=ctx.targets,
        base_lines=cook_base(recipe, ctx.catalogue, portions), flex_lines=cook_flex(plates),
        pot=pot_shares(plates), meals=sorted({p.meal for p in plates}, key=MEALS.index),
        plates={(p.person, p.meal): p for p in plates}, people=PEOPLE, catalogue=ctx.catalogue,
    )


@bp.route("/recipe/<slug>")
def recipe(slug: str):
    session = db()
    r = get_recipe(session, slug)
    if r is None:
        abort(404)
    ctx = load_context(session)
    check = ctx.check(r, get_exclusion_rules(session))
    return render_template("recipe.html", slot=None, **card_context(ctx, r, check, r.servings))


@bp.route("/cook/<int:slot_id>", methods=["GET", "POST"])
def cook(slot_id: int):
    """The recipe card for a planned night, with each person's portion changes."""
    session = db()
    slot = get_slot(session, slot_id)
    if slot is None or not slot.recipe_slug:
        abort(404)
    r = get_recipe(session, slot.recipe_slug)
    ctx = load_context(session)

    if request.method == "POST":
        options = {comp.component: {o.ingredient for o in comp.options} for comp in r.flexible}
        for person in PEOPLE:
            for meal in meals_for_portions(slot.portions):
                for comp in r.flexible:
                    prefix = f"{person}-{meal}-{comp.component}"
                    option = request.form.get(f"{prefix}-option") or None
                    grams_text = (request.form.get(f"{prefix}-grams") or "").strip()
                    if option is not None and option not in options[comp.component]:
                        abort(400)
                    try:
                        grams = float(grams_text) if grams_text else None
                    except ValueError:
                        flash(f"'{grams_text}' isn't a number of grams.", "error")
                        return redirect(url_for("main.cook", slot_id=slot_id))
                    if grams is not None and not 0 <= grams <= 1000:
                        flash("Grams must be between 0 and 1000.", "error")
                        return redirect(url_for("main.cook", slot_id=slot_id))
                    save_choice(slot, person, meal, comp.component, option, grams)
        session.commit()
        flash("Portions updated. The shopping list has been updated too.", "ok")
        return redirect(url_for("main.cook", slot_id=slot_id))

    choices = get_choices(slot)
    check = ctx.check(r, get_exclusion_rules(session), slot.portions, choices)
    return render_template("recipe.html", slot=slot, choices=choices, week_start=slot.week.start,
                           **card_context(ctx, r, check, slot.portions))


def _week_or_404(start: str):
    week_start = date.fromisoformat(start)
    if week_start.weekday() != 5:
        abort(404)
    return ensure_week(db(), week_start)


@bp.route("/shopping")
def shopping_now():
    return redirect(url_for("main.shopping", start=week_start_for(today()).isoformat()))


@bp.route("/shopping/<start>")
def shopping(start: str):
    session = db()
    week_row = _week_or_404(start)
    items = shopping_list(session, week_row)
    ticks = get_ticks(session, week_row)
    to_buy = [i for i in items if not i.staple]
    return render_template(
        "shopping.html", week_start=week_row.start, groups=group_by_aisle(to_buy),
        staples=sorted((i for i in items if i.staple), key=lambda i: i.ingredient.name),
        ticks=ticks, left=sum(1 for i in to_buy if i.key not in ticks), total=len(to_buy),
        cooks=sum(1 for s in week_row.slots if s.recipe_slug))


@bp.route("/shopping/<start>/tick/<key>", methods=["POST"])
def tick(start: str, key: str):
    session = db()
    week_row = _week_or_404(start)
    item = next((i for i in shopping_list(session, week_row) if i.key == key), None)
    if item is None:
        abort(404)
    toggle_tick(session, week_row, key)
    session.commit()
    if request.headers.get("HX-Request"):  # HTMX: send back just the updated line and the counter
        ticks = get_ticks(session, week_row)
        left = sum(1 for i in shopping_list(session, week_row) if not i.staple and i.key not in ticks)
        return render_template("_shopping_item.html", item=item, ticks=ticks, left=left,
                               week_start=week_row.start)
    return redirect(url_for("main.shopping", start=start))


@bp.route("/shopping/<start>/pantry/<key>", methods=["POST"])
def pantry(start: str, key: str):
    session = db()
    _week_or_404(start)
    if key not in load_context(session).catalogue:
        abort(404)
    in_pantry = toggle_pantry(session, key)
    session.commit()
    flash("Moved to pantry staples." if in_pantry else "Moved back onto the shopping list.", "ok")
    return redirect(url_for("main.shopping", start=start))


@bp.route("/shopping/<start>.txt")
def shopping_text(start: str):
    session = db()
    week_row = _week_or_404(start)
    title = f"Hormonious shopping list - week from Sat {week_row.start.strftime('%d %b')}"
    text = as_text(shopping_list(session, week_row), title, get_ticks(session, week_row))
    return Response(text, mimetype="text/plain; charset=utf-8")


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
