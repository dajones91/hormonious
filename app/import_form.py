"""Read the import review form back into the AI recipe shape.

The form has numbered rows: shared-0-ingredient, shared-0-grams, ... and for each
flexible component flex-0-component, flex-0-default, flex-0-opt-1-ingredient, ...
Rows with no ingredient chosen, or ticked to remove, are dropped.
"""

from werkzeug.datastructures import MultiDict

EXTRA_ROWS = 3  # blank rows offered for adding ingredients or options


def _number(form: MultiDict, name: str, errors: list[str], label: str) -> float | None:
    text = (form.get(name) or "").strip()
    try:
        value = float(text)
    except ValueError:
        errors.append(f"{label}: '{text}' isn't a number")
        return None
    if value < 0:
        errors.append(f"{label} can't be negative")
    return value


def _rows(form: MultiDict, prefix: str) -> list[int]:
    """The row numbers present in the form for a prefix like 'shared-' or 'flex-0-opt-'."""
    numbers = set()
    for key in form.keys():
        if key.startswith(prefix):
            head = key[len(prefix):].split("-", 1)[0]
            if head.isdigit():
                numbers.add(int(head))
    return sorted(numbers)


def recipe_from_form(form: MultiDict) -> tuple[dict, list[str]]:
    errors: list[str] = []
    shared = []
    for i in _rows(form, "shared-"):
        p = f"shared-{i}-"
        key = (form.get(p + "ingredient") or "").strip()
        if not key or form.get(p + "remove"):
            continue
        grams = _number(form, p + "grams", errors, f"Ingredient {key} grams")
        shared.append({"ingredient": key, "grams": grams or 0,
                       "display": (form.get(p + "display") or "").strip() or None,
                       "note": (form.get(p + "note") or "").strip() or None})

    flexible = []
    for c in _rows(form, "flex-"):
        p = f"flex-{c}-"
        default = form.get(p + "default")
        options = []
        for j in _rows(form, p + "opt-"):
            q = f"{p}opt-{j}-"
            key = (form.get(q + "ingredient") or "").strip()
            if not key or form.get(q + "remove"):
                continue
            label = f"{key} portion"
            options.append({
                "ingredient": key,
                "standard_grams": _number(form, q + "standard", errors, label) or 0,
                "min_grams": _number(form, q + "min", errors, label) or 0,
                "max_grams": _number(form, q + "max", errors, label) or 0,
                "default": default == str(j),
            })
        if not options:
            continue
        if not any(o["default"] for o in options):
            options[0]["default"] = True
        flexible.append({"component": form.get(p + "component", "carb"), "options": options,
                         "cook_note": (form.get(p + "cook_note") or "").strip() or None})

    times = {}
    for name in ("active_min", "total_min", "spice"):
        value = _number(form, name, errors, name.replace("_", " "))
        times[name] = int(value) if value is not None else 0
    recipe = {
        "title": (form.get("title") or "").strip(),
        "tier": form.get("tier", "weeknight"),
        "cuisine": (form.get("cuisine") or "").strip() or "Home",
        **times,
        "tags": [t.strip() for t in (form.get("tags") or "").split(",") if t.strip()],
        "shared": shared,
        "flexible": flexible,
        "steps": [s.strip() for s in (form.get("steps") or "").splitlines() if s.strip()],
        "reheat_note": (form.get("reheat_note") or "").strip(),
    }
    if not recipe["title"]:
        errors.append("The recipe needs a title")
    if not shared:
        errors.append("The recipe needs at least one shared ingredient")
    if not recipe["steps"]:
        errors.append("The recipe needs at least one step")
    return recipe, errors
