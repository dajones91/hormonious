"""Recipe import: create a draft from text or a photo, preview it with our checks, then save it."""

from dataclasses import dataclass, field

from pydantic import ValidationError
from sqlalchemy.orm import Session

from ai.generate import AiError, check_answer
from ai.importer import ImportAnswer, ImportCall, call_claude_import, import_prompt, prepare_image
from ai.schema import AiAnswer, AiRecipe
from core.schema import Ingredient, Recipe
from db.models import ImportDraftRow
from db.planner import Context, RecipeCheck, load_context
from db.repo import all_titles_and_slugs, get_exclusion_notes, get_exclusion_rules, save_ingredient, save_recipe


@dataclass
class DraftPreview:
    recipe: Recipe | None  # None when the draft can't be turned into a recipe yet
    problems: list[str]  # must fix before saving (missing fields, unknown ingredients, duplicate title)
    check: RecipeCheck | None  # our usual checks: exclusions and nutrition rules (warnings, not blockers)
    new_ingredients: list[Ingredient] = field(default_factory=list)
    catalogue: dict[str, Ingredient] = field(default_factory=dict)  # ours plus the draft's new ingredients


def create_draft(session: Session, text: str, image: bytes | None, source_url: str | None,
                 call: ImportCall = call_claude_import) -> tuple[ImportDraftRow | None, str, dict]:
    """Ask the AI to read the recipe. Returns (draft or None, the AI's message, token usage)."""
    if not text.strip() and not image:
        raise AiError("Paste some recipe text or choose a photo first.")
    image_b64 = prepare_image(image) if image else None
    ctx = load_context(session)
    system = import_prompt(ctx.catalogue, "\n".join(get_exclusion_notes(session)))
    answer, usage = call(system, text[:20000], image_b64)
    if not answer.is_recipe or answer.recipe is None:
        return None, answer.message or "That doesn't look like a recipe.", usage
    draft = ImportDraftRow(data=answer.model_dump(), source_url=(source_url or None), note=answer.message)
    session.add(draft)
    session.commit()
    return draft, answer.message, usage


def preview(session: Session, draft: ImportDraftRow) -> DraftPreview:
    """Turn a draft into a recipe and run our checks, without saving anything."""
    ctx = load_context(session)
    answer = ImportAnswer.model_validate(draft.data)
    titles, slugs = all_titles_and_slugs(session)
    as_ai = AiAnswer(recipe=answer.recipe, new_ingredients=answer.new_ingredients)
    recipe, new, problems = check_answer(as_ai, ctx.catalogue, lambda r, c: [], {t.lower() for t in titles}, slugs)
    if recipe is None:
        return DraftPreview(None, problems, None)
    catalogue = {**ctx.catalogue, **{i.key: i for i in new}}
    recipe = recipe.model_copy(update={"source": "imported", "source_url": draft.source_url})
    check = Context(catalogue, ctx.targets, ctx.settings, ctx.rule_settings).check(recipe, get_exclusion_rules(session))
    return DraftPreview(recipe, [], check, new, catalogue)


def update_draft(session: Session, draft: ImportDraftRow, recipe_data: dict) -> list[str]:
    """Replace the draft's recipe with our edits. Returns problems if the edits aren't valid."""
    try:
        recipe = AiRecipe.model_validate(recipe_data)
    except ValidationError as e:
        return [f"{'.'.join(map(str, err['loc']))}: {err['msg']}" for err in e.errors()]
    data = dict(draft.data)
    data["recipe"] = recipe.model_dump()
    draft.data = data  # reassign so SQLAlchemy notices the JSON changed
    session.commit()
    return []


def save_draft(session: Session, draft: ImportDraftRow) -> tuple[Recipe | None, list[str]]:
    """Save the reviewed recipe to the library and delete the draft."""
    result = preview(session, draft)
    if result.recipe is None:
        return None, result.problems
    for ingredient in result.new_ingredients:
        save_ingredient(session, ingredient)
    session.flush()
    save_recipe(session, result.recipe)
    session.delete(draft)
    session.commit()
    return result.recipe, []
