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
- Hosting: PythonAnywhere free tier. Fallback: Render + Neon Postgres if the outbound allowlist blocks api.anthropic.com (verify before stage 5).

## Conventions
- UK English, metric units, UK ingredient names and Tesco pack sizes and aisles.
- Store weights in grams **in the state they're bought or weighed** (raw or dry). Cooked weight = grams × the ingredient's `cooked_yield`.
- Nutrition is per 100 g in the ingredient table (CoFID first, then Open Food Facts/pack label, then AI estimate flagged `verified=False`). Show values rounded with "≈ estimated".
- Core logic goes in `core/` as plain Python with no Flask imports, and is fully unit-tested.
- Health wording: "designed to support" / "in line with". Never medical claims. Show a "not medical advice" note.
- Secrets live only in `.env` (git-ignored). The API key is never sent to the frontend.

## Household rules
- Exclusions are hard rules. If either person excludes something, the recipe is never suggested.
  - Jade: all fish, shellfish and anchovies. **Exceptions:** fish sauce, shrimp paste, breaded/battered cod (these may be suggested). Mushrooms in every form, including stock and powder.
  - Dale: whole pieces of fruit, fresh or dried. Juice and zest are OK. Tomato, pepper, avocado, olives and coconut count as savoury and are OK.
- Matching works by food family tags on ingredients, then a keyword safety net, then the exception list.
- Default per-plated-portion rules (configurable): protein ≥ 35 g, fibre ≥ 8 g, Jade's carbs ≤ 45 g, low-GI carbs, little or no added sugar, no refined white carb base without a swap, protein + veg + healthy fat.
- Week = Saturday → Friday. The shop arrives Friday or Saturday. The new menu is ready each Monday.
- Mon–Thu cooks 4 portions (2 dinners + 2 next-day lunches). No plan on Friday by default. Weekend special is optional: Saturday = 2 portions, Sunday = 4 (covers Monday lunch).
- Weeknight recipes: ≤ 45 min total (ideally 30). Weekend special: ≤ ~90 min.
- Shared base split: recipe ratio → profile (fixed or by protein target) → 50/50. Flexible portion = min(kcal-fit, carb-fit), clamped and rounded to 5 g.
- Repetition: never last week's recipes. Cooldown uses the lower of the two ratings: 5★ 2–3 weeks, 4★ 4–6, 3★ ~10, ≤2★ never.
- Login is one shared family password. Each device then picks "Dale" or "Jade".

## Stage progress
- [x] 0 PC setup, git, GitHub repo (private: github.com/dajones91/hormonious, branch `main`)
- [ ] 1 Recipe model, ingredients, exclusions, seed library
- [ ] 2 Profiles, targets, menu generation, planning
- [ ] 3 Recipe cards, portions, shopping list
- [ ] 4 Ratings and repetition
- [ ] 5 AI recipe generation
- [ ] 6 Recipe import (text/photo)
- [ ] 7 Login, deploy, phone install
- [ ] 8 (Optional) weekly email digest
