"""Web pages: the week plan, recipe cards, the shopping list, the library and profiles."""

from datetime import date, timedelta

from flask import Blueprint, Response, abort, current_app, flash, g, redirect, render_template, request, url_for

from ai.generate import AiError, call_claude
from ai.importer import call_claude_import
from app.import_form import EXTRA_ROWS, recipe_from_form
from core.cooking import cook_base, cook_flex, pot_shares
from core.menu import Menu, check_assignment, menu_is_ready, menu_ready_date, week_slots, week_start_for
from core.portions import MEALS, PEOPLE, MealTarget, meals_for_portions
from core.ratings import available_from, household_rating, is_retired
from core.search import matches, search_text
from core.shopping import as_text, group_by_aisle
from db.importing import create_draft, preview, save_draft, update_draft
from db.models import ImportDraftRow
from db.planner import (check_all, ensure_week, generate_and_save, has_plan, household_stars, load_context,
                        make_menu, shopping_list)
from db.repo import (add_rating, get_choices, get_exclusion_rules, get_ratings, get_recipe, get_recipe_source_and_status,
                     get_recipes, get_restores, get_slot, get_slot_ratings, get_ticks, last_cooked, restore_recipe,
                     save_choice, save_target, set_recipe_status, set_setting, set_slot, toggle_pantry, toggle_tick)

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


def next_week_banner(session, week_start: date) -> dict | None:
    """On the current week's page, from Monday: next week's menu is ready and not planned yet."""
    current = week_start_for(today())
    upcoming = current + timedelta(days=7)
    if week_start != current or not menu_is_ready(upcoming, today()):
        return None
    next_row = ensure_week(session, upcoming, today())  # builds next week's menu on first view from Monday
    if has_plan(next_row):
        return None
    return {"start": upcoming, "weeknight": len(next_row.weeknight_options), "weekend": len(next_row.weekend_options)}


@bp.route("/week", methods=["GET"])
@bp.route("/week/<start>", methods=["GET", "POST"])
def week(start: str | None = None):
    week_start = date.fromisoformat(start) if start else week_start_for(today())
    if week_start.weekday() != 5:
        abort(404)
    session = db()
    week_row = ensure_week(session, week_start, today())
    recipes = {r.slug: r for r in get_recipes(session)}
    slots = week_slots(week_start, load_context(session).settings["friday_plan"])
    ready = menu_ready_date(week_start)

    if request.method == "POST":
        if week_row is None:
            flash(f"Planning for this week opens on Monday {ready.strftime('%d %b')}.", "error")
            return redirect(url_for("main.week", start=week_start.isoformat()))
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
        open_day = request.form.get("open")
        if open_day:  # "Open recipe card" pressed: the plan is saved, now go to that night's card
            slot = next((s for s in week_row.slots if s.day.isoformat() == open_day), None)
            if slot and slot.recipe_slug:
                return redirect(url_for("main.cook", slot_id=slot.id))
            flash("Plan saved. There's no recipe on that night to open.", "ok")
            return redirect(url_for("main.week", start=week_start.isoformat()))
        flash("Plan saved.", "ok")
        return redirect(url_for("main.week", start=week_start.isoformat()))

    rows = []
    stored = {s.day: s for s in week_row.slots} if week_row else {}
    for slot in slots:
        saved = stored.get(slot.day)
        recipe = recipes.get(saved.recipe_slug) if saved and saved.recipe_slug else None
        rows.append({
            "slot": slot,
            "value": "no-cook" if saved and saved.no_cook else (recipe.slug if recipe else ""),
            "recipe": recipe,
            "slot_id": saved.id if saved else None,
            "rated": get_slot_ratings(session, saved.id) if recipe and slot.day <= today() else None,
            "warnings": check_assignment(slot, recipe) if recipe else [],
        })
    # Saved menu once it's ready; before then an unsaved preview that may still change.
    menu = Menu(week_row.weeknight_options, week_row.weekend_options) if week_row else make_menu(session, week_start)
    on_menu = set(menu.weeknight) | set(menu.weekend)
    return render_template(
        "week.html", week_start=week_start, rows=rows, recipes=recipes, preview=week_row is None,
        weeknight=[recipes[s] for s in menu.weeknight if s in recipes],
        weekend=[recipes[s] for s in menu.weekend if s in recipes],
        others=sorted((r for s, r in recipes.items() if s not in on_menu), key=lambda r: r.title),
        cooking=sum(1 for r in rows if r["recipe"]),
        to_rate=[r for r in rows if r["rated"] is not None and len(r["rated"]) < 2],
        ready=ready, today=today(), is_current=week_start == week_start_for(today()),
        banner=next_week_banner(session, week_start),
        prev_week=(week_start - timedelta(days=7)).isoformat(), next_week=(week_start + timedelta(days=7)).isoformat(),
    )


@bp.route("/recipes")
def recipes():
    session = db()
    ctx = load_context(session)
    checks = check_all(session, ctx)
    stars = household_stars(session)
    texts = {c.recipe.slug: search_text(c.recipe, ctx.catalogue) for c in checks}
    query = request.args.get("q", "").strip()[:100]
    shown = [c for c in checks if matches(texts[c.recipe.slug], query)]
    retired = [c for c in shown if is_retired(stars.get(c.recipe.slug))]
    return render_template("recipes.html", checks=[c for c in shown if c not in retired], retired=retired,
                           stars=stars, query=query, texts=texts, total=len(checks),
                           on_menu=sum(1 for c in checks if c.ok))


def rating_summary(session, slug: str) -> dict:
    """Everything the recipe page shows about how we've rated it and when it can come back."""
    ratings = get_ratings(session, slug).get(slug, [])
    restored_on = get_restores(session).get(slug)
    stars = household_rating(ratings, restored_on)
    last = last_cooked(session, today() + timedelta(days=1)).get(slug)
    opens = available_from(last, stars)
    return {
        "stars": stars, "retired": is_retired(stars), "restored_on": restored_on, "last": last,
        "history": sorted(ratings, key=lambda r: r.on, reverse=True),
        "next_week": opens if opens and opens != date.min else None,
    }


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
    estimates = sorted({ctx.catalogue[k].name for k in r.ingredient_keys()
                        if ctx.catalogue[k].source == "ai-estimate" and not ctx.catalogue[k].verified})
    removed = get_recipe_source_and_status(session, slug)[1] == "removed"
    return render_template("recipe.html", slot=None, rating=rating_summary(session, slug), estimates=estimates,
                           removed=removed,
                           **card_context(ctx, r, check, r.servings))


@bp.route("/recipes/generate", methods=["POST"])
def generate():
    """Ask the AI for a new recipe; it's only saved if it passes every check."""
    tier = request.form.get("tier", "weeknight")
    if tier not in ("weeknight", "weekend"):
        abort(400)
    idea = request.form.get("idea", "").strip()[:200]
    try:
        result = generate_and_save(db(), tier, idea, call=current_app.config.get("AI_CALL") or call_claude)
    except AiError as e:
        flash(str(e), "error")
        return redirect(url_for("main.recipes"))
    cost = f"about {result.cost_usd * 80:.0f}p" if result.cost_usd >= 0.01 else "under 1p"
    if not result.ok:
        last = "; ".join(result.problems[-1][:3])
        flash(f"Sorry, none of the {result.attempts} attempts passed our checks ({cost} used). Last problems: {last}",
              "error")
        return redirect(url_for("main.recipes"))
    tries = "first time" if result.attempts == 1 else f"after {result.attempts} attempts"
    flash(f"New recipe added. It passed all our checks {tries} ({cost}).", "ok")
    return redirect(url_for("main.recipe", slug=result.recipe.slug))


@bp.route("/recipes/import", methods=["POST"])
def import_recipe():
    """Read one of our own recipes from pasted text or a photo, then open it for review."""
    upload = request.files.get("photo")
    image = upload.read() if upload and upload.filename else None
    url = request.form.get("source_url", "").strip()[:500]
    if url and not url.startswith(("http://", "https://")):
        url = ""
    call = current_app.config.get("IMPORT_CALL") or call_claude_import
    try:
        draft, message, usage = create_draft(db(), request.form.get("text", ""), image, url or None, call=call)
    except AiError as e:
        flash(str(e), "error")
        return redirect(url_for("main.recipes"))
    if draft is None:
        flash(f"Couldn't import that: {message}", "error")
        return redirect(url_for("main.recipes"))
    return redirect(url_for("main.import_review", draft_id=draft.id))


@bp.route("/recipes/import/<int:draft_id>", methods=["GET", "POST"])
def import_review(draft_id: int):
    """Check and edit an imported recipe before it goes into the library."""
    session = db()
    draft = session.get(ImportDraftRow, draft_id)
    if draft is None:
        flash("That import has already been saved or discarded.", "error")
        return redirect(url_for("main.recipes"))
    form_errors: list[str] = []
    if request.method == "POST":
        action = request.form.get("action", "check")
        if action == "discard":
            session.delete(draft)
            session.commit()
            flash("Import discarded.", "ok")
            return redirect(url_for("main.recipes"))
        recipe_data, form_errors = recipe_from_form(request.form)
        if not form_errors:
            form_errors = update_draft(session, draft, recipe_data)
        if not form_errors and action == "save":
            recipe, problems = save_draft(session, draft)
            if recipe is not None:
                flash("Recipe added to your library.", "ok")
                return redirect(url_for("main.recipe", slug=recipe.slug))
            form_errors = problems
        if not form_errors:
            return redirect(url_for("main.import_review", draft_id=draft_id))
    result = preview(session, draft)
    names = sorted(((k, i.name) for k, i in {**load_context(session).catalogue, **result.catalogue}.items()),
                   key=lambda kv: kv[1].lower())
    new_keys = {i["key"]: i["name"] for i in draft.data.get("new_ingredients", [])}
    for key, name in new_keys.items():
        if key not in dict(names):
            names.append((key, f"{name} (new)"))
    return render_template("import_review.html", draft=draft, r=draft.data["recipe"], result=result,
                           form_errors=form_errors, ingredient_names=names, extra_rows=EXTRA_ROWS,
                           targets=load_context(session).targets)


@bp.route("/recipe/<slug>/remove", methods=["POST"])
def remove(slug: str):
    """Remove an AI or imported recipe from the library (seed recipes are retired by rating instead)."""
    session = db()
    info = get_recipe_source_and_status(session, slug)
    if info is None or info[0] == "seed":
        abort(404)
    set_recipe_status(session, slug, "removed")
    session.commit()
    flash("Recipe removed from the library.", "ok")
    return redirect(url_for("main.recipes"))


@bp.route("/recipe/<slug>/restore", methods=["POST"])
def restore(slug: str):
    session = db()
    if get_recipe(session, slug) is None:
        abort(404)
    restore_recipe(session, slug, today())
    session.commit()
    flash("Restored. It can come back on the menu, and its old ratings no longer count.", "ok")
    return redirect(url_for("main.recipe", slug=slug))


def choice_groups(ctx, portions: int) -> list[tuple[str, tuple[str, ...]]]:
    """How the portion form is split: one choice per person covering dinner and lunch when
    lunch matches dinner, otherwise one per meal. Each group is (form key, meals it covers)."""
    meals = meals_for_portions(portions)
    if ctx.settings.get("same_lunch_as_dinner", True) and len(meals) > 1:
        return [("both", meals)]
    return [(m, (m,)) for m in meals]


@bp.route("/cook/<int:slot_id>", methods=["GET", "POST"])
def cook(slot_id: int):
    """The recipe card for a planned night, with each person's portion changes."""
    session = db()
    slot = get_slot(session, slot_id)
    if slot is None or not slot.recipe_slug:
        abort(404)
    r = get_recipe(session, slot.recipe_slug)
    ctx = load_context(session)

    groups = choice_groups(ctx, slot.portions)
    if request.method == "POST":
        options = {comp.component: {o.ingredient for o in comp.options} for comp in r.flexible}
        for person in PEOPLE:
            for group, meals in groups:
                for comp in r.flexible:
                    prefix = f"{person}-{group}-{comp.component}"
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
                    for meal in meals:
                        save_choice(slot, person, meal, comp.component, option, grams)
        session.commit()
        flash("Portions updated. The shopping list has been updated too.", "ok")
        return redirect(url_for("main.cook", slot_id=slot_id))

    choices = get_choices(slot)
    check = ctx.check(r, get_exclusion_rules(session), slot.portions, choices)
    return render_template("recipe.html", slot=slot, choices=choices, groups=groups, week_start=slot.week.start,
                           can_rate=slot.day <= today(), slot_ratings=get_slot_ratings(session, slot.id),
                           rating=rating_summary(session, r.slug),
                           **card_context(ctx, r, check, slot.portions))


@bp.route("/cook/<int:slot_id>/rate", methods=["POST"])
def rate(slot_id: int):
    """After cooking: each of us rates the recipe 1-5, with an optional note."""
    session = db()
    slot = get_slot(session, slot_id)
    if slot is None or not slot.recipe_slug:
        abort(404)
    if slot.day > today():
        flash("You can rate this once you've cooked it.", "error")
        return redirect(url_for("main.cook", slot_id=slot_id))
    saved = 0
    for person in PEOPLE:
        stars_text = request.form.get(f"{person}-stars", "")
        if not stars_text:
            continue
        if stars_text not in {"1", "2", "3", "4", "5"}:
            abort(400)
        note = request.form.get(f"{person}-note", "").strip()[:500]
        add_rating(session, slot.recipe_slug, person, int(stars_text), note, today(), slot_id=slot.id)
        saved += 1
    session.commit()
    flash("Thanks, rating saved." if saved else "Pick some stars first.", "ok" if saved else "error")
    return redirect(url_for("main.cook", slot_id=slot_id) + "#rate")


def _week_or_404(start: str):
    """The saved week for a shopping page, or 404 if it's not a Saturday or not open for planning yet."""
    week_start = date.fromisoformat(start)
    week_row = ensure_week(db(), week_start, today()) if week_start.weekday() == 5 else None
    if week_row is None:
        abort(404)
    return week_row


@bp.route("/shopping")
def shopping_now():
    """The list you're likely shopping for: next week's once it's being planned, else this week's."""
    current = week_start_for(today())
    upcoming = current + timedelta(days=7)
    next_row = ensure_week(db(), upcoming, today()) if menu_is_ready(upcoming, today()) else None
    start = upcoming if has_plan(next_row) else current
    return redirect(url_for("main.shopping", start=start.isoformat()))


@bp.route("/shopping/<start>")
def shopping(start: str):
    session = db()
    week_start = date.fromisoformat(start)
    if week_start.weekday() != 5:
        abort(404)
    weeks = {"prev": (week_start - timedelta(days=7)).isoformat(), "next": (week_start + timedelta(days=7)).isoformat()}
    week_row = ensure_week(session, week_start, today())
    if week_row is None:  # planning hasn't opened for this week yet
        return render_template("shopping.html", week_start=week_start, weeks=weeks, cooks=0, groups=[],
                               staples=[], ticks=set(), left=0, total=0)
    items = shopping_list(session, week_row)
    ticks = get_ticks(session, week_row)
    to_buy = [i for i in items if not i.staple]
    return render_template(
        "shopping.html", week_start=week_row.start, groups=group_by_aisle(to_buy),
        staples=sorted((i for i in items if i.staple), key=lambda i: i.ingredient.name),
        ticks=ticks, left=sum(1 for i in to_buy if i.key not in ticks), total=len(to_buy), weeks=weeks,
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
            set_setting(session, "same_lunch_as_dinner", request.form.get("same_lunch_as_dinner") == "on")
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
