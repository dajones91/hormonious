"""Import one of our own recipes from pasted text or a photo/screenshot.

The AI reads it and fills in our recipe format, mapping ingredients to our
table and suggesting which parts are flexible (usually the carb, with lower-carb
swaps). We then review and edit it before saving.

Photos are shrunk in memory, sent once, and never stored: only the extracted
recipe text is kept, in our private library.
"""

import base64
from io import BytesIO
from typing import Callable

from PIL import Image, ImageOps, UnidentifiedImageError
from pydantic import BaseModel, Field

from ai.generate import RECIPE_FORMAT, AiError, ingredient_table, request_structured
from ai.schema import AiNewIngredient, AiRecipe
from core.schema import Ingredient

MAX_IMAGE_SIDE = 1568  # pixels; larger photos cost more and don't read any better
ImportCall = Callable[[str, str, str | None], tuple["ImportAnswer", dict]]  # (system, text, jpeg base64) -> answer


class ImportAnswer(BaseModel):
    is_recipe: bool = Field(description="false if the text or image isn't a recipe or can't be read")
    message: str = Field(description="short note for us: what you assumed or changed, or why it isn't a recipe")
    recipe: AiRecipe | None
    new_ingredients: list[AiNewIngredient]


def prepare_image(data: bytes) -> str:
    """Shrink a photo or screenshot and return it as base64 JPEG. Nothing is written to disk."""
    try:
        image = Image.open(BytesIO(data))
        image = ImageOps.exif_transpose(image).convert("RGB")  # respect phone rotation
    except (UnidentifiedImageError, OSError):
        raise AiError("Couldn't read that image. Please use a JPEG or PNG photo or screenshot.")
    image.thumbnail((MAX_IMAGE_SIDE, MAX_IMAGE_SIDE))
    out = BytesIO()
    image.save(out, format="JPEG", quality=85)
    return base64.standard_b64encode(out.getvalue()).decode("ascii")


def call_claude_import(system: str, text: str, image_b64: str | None) -> tuple[ImportAnswer, dict]:
    content: list[dict] = []
    if image_b64:
        content.append({"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": image_b64}})
    ask = "Please turn this into one of our recipes."
    if text.strip():
        ask += f"\n\nThe recipe text:\n{text.strip()}"
    elif image_b64:
        ask += " The recipe is in the image."
    content.append({"type": "text", "text": ask})
    return request_structured(system, content, ImportAnswer)


def import_prompt(catalogue: dict[str, Ingredient], exclusions_text: str) -> str:
    return f"""You convert recipes for Hormonious, a private weekly meal planner for a UK couple, Dale and Jade.
They've given you one of their own recipes (pasted text, or a photo or screenshot of a recipe card) to add to
their personal library. Write in UK English with metric units and UK supermarket (Tesco) ingredient names.

# What to do
- Extract the recipe faithfully. Don't invent ingredients or change the dish; if something is unclear
  (missing times, vague amounts), make a sensible estimate and say so in `message`.
- If it isn't a recipe or can't be read, set is_recipe=false, recipe=null and explain in `message`.
- Scale it to make 4 portions (2 dinners + 2 next-day lunch boxes) and convert every amount to grams.
- Split it into our format:
  - The SHARED BASE (protein, veg, sauce) goes in `shared`, with `grams` = the total for all 4 portions.
  - Anything served on the side that's mostly carbs (rice, pasta, noodles, bread, wraps, potatoes, couscous)
    becomes a FLEXIBLE component named "carb", sized per person per meal (`standard_grams` for ONE person).
    Keep the original as the default option, and add one or two sensible lower-carb or low-GI swaps
    (e.g. brown_basmati for white rice, cauliflower_rice, courgette, tenderstem).
  - A sprinkle that people take more or less of (cheese, nuts, seeds) can be a "topping" component.
- tier: "weeknight" if total time is 45 minutes or less, otherwise "weekend".
- Don't remove anything they might not eat: our own checks will flag it. But here is what they exclude,
  so you can mention it in `message` if the recipe contains it:
{exclusions_text}

# Our recipe format
{RECIPE_FORMAT}

# Ingredient table (key | name | weighed state | nutrition per 100 g | GI | flags)
{ingredient_table(catalogue, hide_excluded=False)}
"""
