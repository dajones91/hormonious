"""Generate new recipes with Claude, then check them like any other recipe.

Flow for one recipe:
1. Send our household rules, targets, exclusions and ingredient table, and ask
   for a recipe in the exact AiAnswer format (structured output).
2. Turn the answer into a normal Recipe and run every check: schema, unknown
   ingredients, exclusions, nutrition rules on each person's plate, time limits
   and duplicates.
3. If anything fails, ask again with the list of problems (up to 3 attempts in
   total). Only a recipe that passes everything is returned for saving.
"""

import os
from dataclasses import dataclass, field
from typing import Callable

import anthropic
from pydantic import ValidationError

from ai.schema import AiAnswer, slugify, to_ingredient, to_recipe
from core.schema import Ingredient, Recipe

MODEL = "claude-opus-5-5"
MAX_ATTEMPTS = 3
# Claude Opus 5.5 list prices in US dollars per million tokens, for the rough cost shown after generating.
PRICE_PER_M = {"input": 4.00, "output": 20.00}

Call = Callable[[str, str], tuple[AiAnswer, dict]]  # (system, user) -> (answer, token usage)
Checker = Callable[[Recipe, dict[str, Ingredient]], list[str]]  # recipe, catalogue -> problems


class AiError(Exception):
    """Something went wrong talking to the API (no key, network, refusal...). The message is shown to us."""


@dataclass
class GenerationResult:
    recipe: Recipe | None
    new_ingredients: list[Ingredient]
    attempts: int
    problems: list[list[str]] = field(default_factory=list)  # what was wrong with each failed attempt
    input_tokens: int = 0
    output_tokens: int = 0

    @property
    def ok(self) -> bool:
        return self.recipe is not None

    @property
    def cost_usd(self) -> float:
        return (self.input_tokens * PRICE_PER_M["input"] + self.output_tokens * PRICE_PER_M["output"]) / 1_000_000


def call_claude(system: str, user: str) -> tuple[AiAnswer, dict]:
    """One request to the Anthropic API, returning a validated AiAnswer and the token usage."""
    if not os.getenv("ANTHROPIC_API_KEY"):
        raise AiError("No Anthropic API key found. Add ANTHROPIC_API_KEY to your .env file.")
    client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY from the environment (.env)
    try:
        response = client.messages.parse(
            model=MODEL,
            max_tokens=16000,
            system=system,
            messages=[{"role": "user", "content": user}],
            output_format=AiAnswer,
        )
    except anthropic.AuthenticationError:
        raise AiError("The Anthropic API key was rejected. Check ANTHROPIC_API_KEY in .env.")
    except anthropic.PermissionDeniedError:
        raise AiError("The API key doesn't have permission. Check it in the Anthropic console.")
    except anthropic.RateLimitError:
        raise AiError("Too many requests right now, or the monthly spend limit was reached. Try again later.")
    except anthropic.APIConnectionError:
        raise AiError("Couldn't reach the Anthropic API. Check the internet connection.")
    except anthropic.APIStatusError as e:
        raise AiError(f"The Anthropic API returned an error ({e.status_code}). Try again in a few minutes.")
    except ValidationError:
        raise AiError("The AI's answer wasn't in the expected format.")

    usage = {"input": response.usage.input_tokens, "output": response.usage.output_tokens}
    if response.stop_reason == "refusal":
        raise AiError("The AI declined this request. Try a different idea.")
    if response.stop_reason == "max_tokens" or response.parsed_output is None:
        raise AiError("The AI's answer was cut short. Try again.")
    return response.parsed_output, usage


def check_answer(answer: AiAnswer, catalogue: dict[str, Ingredient], check: Checker,
                 existing_titles: set[str], existing_slugs: set[str]) -> tuple[Recipe | None, list[Ingredient], list[str]]:
    """Turn an answer into a Recipe and list everything wrong with it (empty list = good to save)."""
    problems: list[str] = []
    new: dict[str, Ingredient] = {}
    for n in answer.new_ingredients:
        if n.key in catalogue:
            continue  # already in our table: use ours
        try:
            new[n.key] = to_ingredient(n)
        except ValidationError as e:
            problems.append(f"new ingredient '{n.key}' is invalid: {e.errors()[0]['msg']}")
    full = {**catalogue, **new}

    used = {i.ingredient for i in answer.recipe.shared} | {
        o.ingredient for c in answer.recipe.flexible for o in c.options}
    unknown = sorted(used - full.keys())
    if unknown:
        problems.append("uses ingredients that are neither in the table nor in new_ingredients: " + ", ".join(unknown))
    if answer.recipe.title.strip().lower() in existing_titles:
        problems.append(f"we already have a recipe called '{answer.recipe.title}'")
    if problems:
        return None, [], problems

    slug, n = slugify(answer.recipe.title), 2
    base = slug
    while slug in existing_slugs:
        slug, n = f"{base}-{n}", n + 1
    try:
        recipe = to_recipe(answer.recipe, slug)
    except ValidationError as e:
        return None, [], [f"{'.'.join(map(str, err['loc']))}: {err['msg']}" for err in e.errors()]

    problems += check(recipe, full)
    used_new = [ing for k, ing in new.items() if k in recipe.ingredient_keys()]
    return (recipe if not problems else None), used_new, problems


def generate_recipe(system: str, tier: str, idea: str, catalogue: dict[str, Ingredient], check: Checker,
                    existing_titles: set[str], existing_slugs: set[str], call: Call = call_claude,
                    max_attempts: int = MAX_ATTEMPTS) -> GenerationResult:
    """Ask for a recipe, check it, and retry with feedback until it passes or we run out of attempts."""
    result = GenerationResult(None, [], 0)
    titles = {t.lower() for t in existing_titles}
    feedback = ""
    for attempt in range(1, max_attempts + 1):
        result.attempts = attempt
        answer, usage = call(system, user_prompt(tier, idea) + feedback)
        result.input_tokens += usage.get("input", 0)
        result.output_tokens += usage.get("output", 0)
        recipe, new, problems = check_answer(answer, catalogue, check, titles, existing_slugs)
        if recipe is not None:
            result.recipe, result.new_ingredients = recipe, new
            return result
        result.problems.append(problems)
        feedback = (
            "\n\nYour previous attempt was rejected by our checks. Write a new version that fixes every problem:\n"
            + "\n".join(f"- {p}" for p in problems)
            + f"\n\nPrevious attempt (for reference):\n{answer.recipe.model_dump_json()}"
        )
    return result


def user_prompt(tier: str, idea: str) -> str:
    kind = ("a WEEKNIGHT recipe: total time 45 minutes or less (ideally about 30), cooked as 4 portions "
            "(2 dinners tonight + 2 lunch boxes tomorrow), so it must reheat well or be good cold"
            if tier == "weeknight" else
            "a WEEKEND SPECIAL: up to about 90 minutes, a bit more indulgent but still following the "
            "nutrition rules loosely")
    ask = f"Please create {kind}."
    if idea.strip():
        ask += f"\nOur idea for this one: {idea.strip()}"
    return ask + "\nMake it something different from the recipes we already have."


def system_prompt(catalogue: dict[str, Ingredient], targets_text: str, exclusions_text: str,
                  existing_titles: list[str]) -> str:
    """Everything Claude needs to know about our household, rules and recipe format."""
    table = "\n".join(
        f"{i.key} | {i.name} | {i.state} | {i.kcal:.0f} kcal, {i.protein:g} P, {i.carbs:g} C, {i.fibre:g} fibre, "
        f"{i.fat:g} fat per 100 g | GI {i.gi} | {','.join(sorted(i.flags)) or '-'}"
        for i in sorted(catalogue.values(), key=lambda i: i.key)
        if not (i.families & {"salmon", "cod", "prawn", "anchovy", "mushroom", "fresh_fruit", "dried_fruit",
                              "fruit_preserve", "mycoprotein", "meat_substitute", "paneer", "oyster"})
    )
    titles = "\n".join(f"- {t}" for t in sorted(existing_titles))
    return f"""You write recipes for Hormonious, a private weekly meal planner for a UK couple, Dale and Jade.
Write in UK English with metric units and UK supermarket (Tesco) ingredient names.

# Who it's for
Jade has PMOS (formerly PCOS) and wants food designed to support insulin sensitivity: high protein,
high fibre, carbs mainly from low-GI, high-fibre sources (pulses, wholegrains, vegetables), little or no
added sugar. They both go to the gym, so high protein matters for every meal. Don't make medical claims.

# Hard exclusions (never use these, in any form)
{exclusions_text}

# Per-person targets (each person's plated portion, per meal)
{targets_text}
Every meal must pair protein + vegetables + some healthy fat (e.g. olive oil, nuts, seeds, avocado).
Refined white carbs (white rice, white pasta) may only appear as a flexible option alongside a low-GI swap.

# How our recipes work
- The SHARED BASE (protein, veg, sauce) is cooked once for 4 portions and split between the two of us.
  List it in `shared` with `grams` = the TOTAL for all 4 portions.
- Make the shared base carry the protein and fibre: for 4 portions aim for at least 150 g protein,
  at least 32 g fibre and about 1600-1900 kcal in total, so each quarter gives about 38 g protein,
  8 g fibre and 400-475 kcal before any carb. Use lean protein and plenty of veg and pulses.
- FLEXIBLE components are sized per person to fit their targets: usually the carb, sometimes a topping
  (cheese, nuts). Give `standard_grams` for ONE person's portion, plus sensible min/max. A carb component
  must have a low-GI default and at least one lower-carb swap (e.g. cauliflower_rice, courgette,
  tenderstem). Exactly one option per component has default=true.
- All weights are as bought/weighed: raw meat and veg, DRY rice/pasta/grains, DRAINED tinned beans.
- Use ingredient keys from the table below wherever possible. Only if you truly need something else,
  add it to `new_ingredients` with honest per-100 g nutrition (as weighed), a typical Tesco pack size and
  the aisle. Keep new ingredients to a minimum.
- Spoon amounts: 1 tbsp oil = 14 g, 1 tsp ground spice = 2-3 g, 1 garlic clove = 5 g.
- `steps`: clear numbered-style steps without the numbers, including when to cook the flexible carb.
  Don't say how to divide the food between people or into equal portions: the app gives each person's
  share. End with a step like "Plate using the plating guide, then box the lunch portions once cooled."
- `reheat_note`: how to reheat the lunch box (or that it's good cold), and what to pack separately.
- `tags` from: high-protein, low-GI, lunchbox-friendly, good-cold, freezer-friendly, one-pot, traybake,
  weekend-special, fakeaway, vegetarian. Weeknight recipes MUST include lunchbox-friendly.
- Spice: they like a fair amount but nothing over the top (max 2 of 3).

# Ingredient table (key | name | weighed state | nutrition per 100 g | GI | flags)
{table}

# Recipes we already have (don't repeat these)
{titles}
"""
