# Hormonious – CLAUDE.md

A private weekly meal planner for Dale and Jade, replacing Gousto. Full plan and reasoning: [PLAN.md](PLAN.md).

## Working with Dale
- Dale knows Python and SQL but is new to app building and Claude Code. Explain decisions in plain terms.
- Explain every command before asking Dale to run it.
- Build in small stages. Each stage must run, be committed to git, and end with "how to run and test it yourself". **Stop for Dale's approval at the end of each stage.**
- Keep this file up to date when decisions change.

## Stack (decided)
- Python 3.12+, Flask, Jinja templates, HTMX, plain CSS. No JS framework.
- SQLite via SQLAlchemy 2.0, with Alembic for migrations. Pydantic for the recipe schema and AI-output validation.
- pytest for tests. The official `anthropic` SDK, model `claude-opus-5-5`.
- PWA: manifest plus a home-screen install on iPhone (Safari). A Windows laptop uses the browser.
- Hosting: PythonAnywhere free tier. `api.anthropic.com` is on its free-account allowlist (checked 2026-10-29). Fallback: Render + Neon Postgres.

## Design direction (agreed 2026-10-28)
- **Warm and healthy** feel (Jade's call, 2026-10-29; replaces the earlier bright blue and duck egg). Brand colour **light chocolate brown** (`--choc` #9a6b4b), used for the header with white text. Buttons and links use a deeper chocolate (`--brand` #7a4f33). The background is cream (`--bg` #faf6f0), with sage green (`--sage` #6f8f5c) for tags and a healthy accent, and honey (`--sun`) for highlights. Dale's plates are chocolate, Jade's are sage. Our own look, never a copy of any brand.
- **Always light mode**: no dark-mode switching.
- Inspiration: therandomrecipe.com. Grid recipe cards with a landscape photo, a category chip on the image, the title, and a stats row (time, servings) with clear action buttons. On phones, use a bottom tab bar instead of a mega-menu.
- **AI-generated food pictures** on recipe cards. Claude can't make images, so this needs a separate image API (choose the provider when we build it); store our own generated images only.
- Stay on Flask + Jinja + HTMX + plain CSS (design tokens in `:root`). No React/Node build step.
- Build Stage 3 screens in this style. Do a full design pass after Stage 3.

## Conventions
- UK English, metric units, UK ingredient names and Tesco pack sizes and aisles.
- Store weights in grams **in the state they're bought or weighed** (raw or dry). Cooked weight = grams × the ingredient's `cooked_yield`.
- Nutrition is per 100 g in the ingredient table (CoFID first, then Open Food Facts/pack label, then AI estimate flagged `verified=False`). Show values rounded with "≈ estimated".
- Core logic goes in `core/` as plain Python with no Flask imports, and is fully unit-tested.
- Health wording: "designed to support" / "in line with". Never medical claims. Show a "not medical advice" note.
- Secrets live only in `.env` (git-ignored). The API key is never sent to the frontend.

## Code map
- `core/schema.py`: Pydantic models (Ingredient, Recipe, RecipeItem, FlexComponent, FlexOption). Shared-base grams are totals for `servings`; flex grams are per person, per meal.
- `core/families.py`: family hierarchy (`PARENTS`) and the keyword safety net (`KEYWORD_RULES`, ordered; a matched phrase is blanked before later rules run).
- `core/exclusions.py`: rule = family + exceptions, checked per family. `check_recipe` covers shared items and every swap option.
- `core/portions.py`: base shares (recipe ratio > settings `split_mode` even/protein/fixed), `build_plate` per person x meal. Toppings and veg swaps are standard size; the carb = min(kcal fit, carb fit), clamped, rounded to 5 g (whole items for `pack_unit=each`), under 1/5 of standard means none, under 1/2 means auto veg swap if one exists.
- `core/rules.py`: `check_plate` (on rounded values), `check_structure`, `validate` (weekend fails become warns). `core/menu.py`: Sat-Fri `week_slots`, `build_menu` (seeded by week start; skips anything cooked in the 7 days before), `check_assignment`.
- `db/planner.py`: `load_context`, `check_all`, `ensure_week` (menu built lazily on first view, stored in `week`). Cook history comes from `plan_slot` rows (no separate log).
- `core/cooking.py`: `cook_base` (scaled shared base), `cook_flex` (flex totals + each plate's %), `pot_shares`. `core/shopping.py`: `build_list` (base x portions/servings + every plate's flex grams), `choose_packs` (least over, then fewest packs; loose `each` items are counted), `group_by_aisle` (`AISLE_ORDER`), `as_text`.
- Library search (`core/search.py`): every query word must appear in the title, cuisine, tier, tags or any ingredient (including swaps). `/recipes?q=` filters on the server; each card's `data-search` lets the page filter live as you type.
- AI generation: `ai/schema.py` (AiAnswer = the structured output shape; `to_recipe`/`to_ingredient`), `ai/generate.py` (`call_claude` uses `client.messages.parse(output_format=AiAnswer)` with `claude-opus-5-5`; `check_answer`; `generate_recipe` retries up to 3 times with the problems as feedback), `db/planner.generate_and_save` (runs the normal exclusion + per-plate rule checks and saves only on a pass). New AI ingredients are saved with `source=ai-estimate`, `verified=False`, and families from `classify_name`. AI/imported recipes can be removed (`status=removed`); seed recipes can't. Tests inject a fake via `app.config['AI_CALL']` or the `call=` argument, so no API key or spend is needed. CLI: `manage.py generate`.
- Import: `ai/importer.py` (`ImportAnswer` = is_recipe + message + AiRecipe + new ingredients; `prepare_image` shrinks to 1568 px JPEG in memory, never stored; `import_prompt` keeps the dish faithful, scales to 4 portions, makes side carbs flexible with swaps). `db/importing.py`: `create_draft` → `import_draft` row (JSON, no image), `preview` (normal checks; exclusions/rule fails are warnings, not blockers), `update_draft`, `save_draft` (`source=imported`, keeps `source_url`). Review form: `/recipes/import/<id>`, parsed by `app/import_form.py`. Tests inject `app.config['IMPORT_CALL']`. `ai/generate.request_structured` is the single API call for both features; shared prompt pieces are `RECIPE_FORMAT` and `ingredient_table`.
- Ratings live in `rating` (per person, optionally per `plan_slot`; re-rating a night replaces it). Restores live in `recipe_restore`. Pages: rate on `/cook/<id>` (POST `/cook/<id>/rate`, only once the day has come), restore via POST `/recipe/<slug>/restore`; the Week tab lists nights still to rate.
- Per-night portion changes live in `portion_choice` (cleared when the night's recipe changes). Pantry staples live in `pantry` (seeded from `staple` flags). Ticks live in `shopping_tick`.
- `app/`: Flask blueprint in `views.py`; `create_app(database_url, today)` (tests pin the date). Pages: `/week` ("Open recipe card" is a submit button named `open`: it saves the plan, then redirects to that night's card), `/cook/<slot_id>` (card plus portion form), `/recipe/<slug>` (preview card), `/shopping/<start>` (+ `.txt`, tick, pantry), `/recipes`, `/profiles`. HTMX (unpkg, pinned 1.9.12) only for shopping ticks; everything else is plain forms. Run commands with `.\.venv\Scripts\python.exe` (Dale's PowerShell blocks Activate.ps1).
- `core/nutrition.py`: per-100 g sums. `core/loaders.py` reads `data/`. `db/`: SQLAlchemy models + repo. `manage.py`: dev commands.
- Run `python -m pytest` and `python manage.py recipes` after changing data. A test requires catalogue `families` to equal `classify_name(name)`.
- No Alembic yet: `manage.py reset-db` rebuilds the dev DB. `make_session_factory` runs `create_all`, so brand-new tables appear without a reset (new *columns* on existing tables still need one). Add Alembic before the first deploy (stage 7).
- Ingredient nutrition is `approx-uk`/unverified. Cross-check against CoFID (needs a download; ask Dale first) before stage 3 portion maths.

## Household rules
- Exclusions are hard rules. If either person excludes something, the recipe is never suggested.
  - Jade: all fish, shellfish and anchovies (incl. Caesar dressing). **Exceptions:** fish sauce, shrimp paste, oyster sauce, Worcestershire sauce, breaded/battered cod (these may be suggested). Mushrooms in every form, including stock and powder.
  - Dale: whole pieces of fruit, fresh or dried, plus chutney and preserved lemon. Juice and zest are OK, and a lemon slice as garnish is OK. Tomato, pepper, avocado, olives and coconut count as savoury and are OK.
  - Household (both): no meat substitutes at all (Quorn/mycoprotein, tofu, tempeh, seitan, TVP, plant-based or "vegan" mince/sausages etc.) and no paneer. Edamame and soy sauce are fine.
- Matching works by food family tags on ingredients, then a keyword safety net, then the exception list.
- Default per-plated-portion rules (configurable): protein ≥ 35 g, fibre ≥ 8 g, Jade's carbs ≤ 45 g, low-GI carbs, little or no added sugar, no refined white carb base without a swap, protein + veg + healthy fat.
- Week = Saturday → Friday. The shop arrives Friday or Saturday. The new menu is ready each Monday:
  - The Week tab always opens on the **current** week (`week_start_for` = the Saturday on or before today).
  - A week's menu is built and saved on first view from its Monday (`menu_is_ready`). Before that, the page is an unsaved
    preview with no plan form. An unplanned week saved early is deleted and rebuilt on its Monday.
  - From Monday, the current week's page shows a "Next week's menu is ready" banner until next week has any plan.
  - The Shopping tab opens next week's list once next week has a plan, otherwise this week's.
  - Outside-the-app alerts (iPhone web push in stage 7, or the stage 8 Monday email) are not built yet.
- Mon–Thu cooks 4 portions (2 dinners + 2 next-day lunches). No plan on Friday by default. Weekend special is optional: Saturday = 2 portions, Sunday = 4 (covers Monday lunch).
- Weeknight recipes: ≤ 45 min total (ideally 30). Weekend special: ≤ ~90 min.
- Shared base split: recipe ratio → profile (fixed or by protein target) → 50/50. Flexible portion = min(kcal-fit, carb-fit), clamped and rounded to 5 g.
- Targets are **live** (Dale's decision, 2026-10-29): portions are computed on every page view, so a profile change immediately resizes every card and shopping list, including weeks already shopped for. Saved menus and manual portion choices don't change. Don't add per-week locking unless asked.
- Lunch box = dinner (setting `same_lunch_as_dinner`, default on, Dale's request 2026-10-29): each person's flexible part is sized once against a target halfway between their dinner and lunch targets, keeping the stricter carb cap. One portion choice per person covers both meals (form key `both`).
- Repetition (`core/ratings.py`): household rating = lower of each person's latest rating since any restore (or the only one). Cooldown in whole Sat–Fri weeks after the week we had it: 5★ 2, 4★ 4, 3★ 10, ≤2★ never (retired until restored; restore ignores ratings up to and including the restore day). **No rating = neutral**: 2-week cooldown, no penalty (Dale: forgetting to rate doesn't mean we disliked it). Menu: ~60% favourites (≥4★, most overdue first), rest untried/unrated (never-cooked get a small boost), 3★ only now and then; settings `cooldown_weeks`, `favourite_share`.
- Login is one shared family password. Each device then picks "Dale" or "Jade".

## Stage progress
- [x] 0 PC setup, git, GitHub repo (private: github.com/dajones91/hormonious, branch `main`)
- [x] 1 Recipe model, ingredients, exclusions, seed library (branch `stage-1/recipes-exclusions`)
- [x] 2 Profiles, targets, menu generation, planning (branch `stage-2/profiles-menu-planning`; portion maths landed here too because rule checks need per-person plates)
- [x] 3 Recipe cards, portions, shopping list (branch `stage-3/cards-shopping`; new bold-blue style and phone tab bar applied app-wide)
- [x] 4 Ratings and repetition (branch `stage-4/ratings`)
- [x] 5 AI recipe generation (branch `stage-5/ai-recipes`; built and tested with a fake AI, live run needs Dale's API key). AI food pictures still to do (image provider not chosen)
- [x] 6 Recipe import (text/photo) (branch `stage-6/recipe-import`; tested with a fake AI)
- [ ] 7 Login, deploy, phone install
- [ ] 8 (Optional) weekly email digest
