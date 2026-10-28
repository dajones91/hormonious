# Hormonious – project plan (draft for approval)

Status: **approved by Dale on 2026-10-28**, with the section 14 answers recorded below.

---

## 1. What I've taken from your answers

| Topic | Decision |
|---|---|
| Fish | Excludes all fish, shellfish and anchovies. **Exceptions:** fish sauce, shrimp paste (Thai cooking) and breaded/battered cod, which the app *may* suggest. |
| Fruit (Dale) | Excludes whole pieces of fruit, fresh or dried (e.g. mango chunks, raisins, apricots in a tagine). Juice and zest are fine. Tomatoes, peppers, avocado, olives and coconut milk count as savoury, so they're allowed. |
| Mushrooms (Jade) | Excludes all forms, including mushroom stock and powder. |
| Week shape | The week runs **Saturday → Friday**. The food shop arrives on the Friday or Saturday before. **The new menu is ready every Monday**, giving you Monday to Thursday to pick before ordering. |
| Monday lunch | When the weekend special is cooked on **Sunday**, it makes 4 portions (2 Sunday dinners + 2 Monday lunches), so it needs to be lunchbox-friendly. A Saturday special makes 2 portions. Both are configurable. |
| Lunch sizing | The shared base is split the same way at dinner and lunch. The flexible part is sized separately for each meal so it hits that meal's target. |
| Lunches | Reheat-friendly is the default (Dale has a work microwave, and Jade mostly works from home). Recipes that also eat well cold get an extra "good cold" tag, useful for Jade's office days. |
| Spice | Medium-hot is fine; nothing extreme. Any cuisine. |
| Kitchen kit | Everything, so recipes may use an air fryer, slow cooker, blender or food processor. Weeknight recipes still have to fit the 45-minute limit. A slow-cooker recipe counts by its *active* time only if it can be started in the morning (flagged as "start before work"). |
| Shop | Tesco pack sizes and aisle order by default. |
| Devices | Two iPhones plus a Windows laptop (just a web browser, no install needed). |
| Login | One shared family password. After logging in, each device asks "Who's this? Dale / Jade" and remembers the answer (you can switch at any time). That's how ratings and portion changes know who you are. |
| Budget | Under £5 a month in total. |

---

## 2. Decision 1 – stack and hosting

**Constraints:** two iPhones and a laptop, shared data, free or nearly free, Python you can read, home-screen install.

| Option | Pros | Cons |
|---|---|---|
| **A. Flask + HTMX web app (PWA) on PythonAnywhere free tier, SQLite database** | Almost all Python. HTMX means pages update without writing a JavaScript app; it's a few HTML attributes. The database is a single file you can open with SQL tools you already know. The host is always on with no "waking up" delay, includes HTTPS (needed for a home-screen app on iPhone), and costs £0. | The free tier only allows outbound requests to an approved list of sites. I believe `api.anthropic.com` is on it, but **I'll verify this before stage 5**. You have to click "extend" on the free web app every 3 months. One app only, on a `yourname.pythonanywhere.com` address. |
| **B. Same app on Render (free) + Neon Postgres (free)** | Also free and Python. Deploys straight from GitHub. Postgres is a "real" database. | The free tier goes to sleep after ~15 minutes idle, so the first tap takes 30–60 seconds. That's annoying at the supermarket. Two services to manage, and no plain file to back up. |
| **C. Streamlit Community Cloud** | Pure Python, very quick to start. | It looks and behaves like a data dashboard, not a phone app. Weak home-screen and offline support, ticking off a shopping list is clunky, and it still needs an external database for shared data. |
| **D. Weekly email workflow** (email the menu, reply with picks) | No app to open, and it works anywhere. | Parsing email replies is fiddly and fragile. You can't tick off a shopping list, adjust portions or read a cooking card well in an email. It also needs an email-sending service and inbound-mail handling. Better as an **add-on** than the main app. |

**Recommendation: A.** It's Flask (Python), Jinja templates (HTML with `{{ placeholders }}`), HTMX for interactivity, a small CSS file, SQLite, and SQLAlchemy for the database layer with Alembic for schema changes. The app is a Progressive Web App: you "Add to Home Screen" in Safari and it opens full-screen like an app. **If the PythonAnywhere allowlist check fails, we switch to B.** The code is identical; only the deployment changes. The weekly email digest (stage 8) can be added later as a one-way "here's this week's menu, tap to pick" email.

Supporting tools: `pytest` for tests, `pydantic` to define and check the recipe JSON schema (very handy for validating AI output), and the official `anthropic` Python SDK.

---

## 3. Decision 2 – how nutrition is calculated

| Approach | Pros | Cons |
|---|---|---|
| AI estimates per recipe | Zero setup | Not consistent: the same recipe can get different numbers each time. Unacceptable when Jade's portion sizes are calculated from it. |
| **UK CoFID** (McCance & Widdowson, free gov.uk download) | UK foods and names, lab-measured values, often has both raw and cooked forms (e.g. "rice, white, boiled") | Excel file, generic foods only (no brands) |
| USDA FoodData Central | Huge, free API | American names and products |
| Open Food Facts | Real branded UK products (e.g. Tesco lentil pasta) | Crowd-sourced, so quality varies |

**Recommendation for the MVP:** calculate from a **local ingredient table** in our database. Each ingredient stores nutrition per 100 g in a stated state (raw, dry or cooked).
- Values come from **CoFID** first. For a branded product like lentil pasta or a specific wrap, we use **Open Food Facts** or the pack label, entered once.
- The seed library's ~150 ingredients get checked CoFID values.
- When an AI-generated or imported recipe uses an ingredient we don't have, the AI suggests the closest CoFID match or estimates values. The ingredient is marked **"unverified"** until one of you confirms it on a simple review screen.
- **How estimates are shown:** every figure is rounded (kcal to the nearest 10, macros to whole grams) and labelled "≈ estimated". A small ⚠ appears when any ingredient in the portion is unverified. Each card has a short footnote: values are estimates from UK food composition data, and real ingredients vary by roughly ±10–15%.

---

## 4. Decision 3 – the portion calculation

**Everything is stored in grams in the state you weigh it when shopping or cooking** (raw chicken, dry rice). Each ingredient also has a **cooked-yield factor** (e.g. dry basmati ×2.6, dry pasta ×2.2, dry red lentils ×2.5, raw chicken thigh ×0.75).

**Step 1 – split the shared base.** The base (protein, veg, sauce) is cooked as 4 portions: 2 dinners and 2 lunches. Each person gets the same base share at dinner and lunch. The share comes from, in order of priority:
1. a ratio set on the recipe (e.g. 55/45), else
2. the profile setting, either a fixed ratio or **"split by protein target"** (e.g. Dale 45 g ÷ (45 + 35) ≈ 56/44), else
3. 50/50.

The default is 50/50, as you asked. I'd suggest trying "split by protein target", because otherwise Dale's protein can only be topped up by the carb.

**Step 2 – size each flexible component, per person, per meal.** After the base, the app works out what's left of that person's target: `remaining kcal = target kcal − base kcal`, and the same for carbs. Then:
- grams that fit the remaining kcal = remaining kcal ÷ kcal per gram of the chosen option
- grams that fit the carb limit = remaining carbs ÷ carbs per gram
- **portion = the smaller of the two**, kept within the option's min/max and rounded to 5 g.

This is simple, explainable arithmetic, with no "optimiser" black box. Swaps (cauliflower rice, extra veg, lentil pasta) are just alternative options with their own nutrition, so the same sum works. Toppings such as cheese or nuts use the same method but are capped by fat or kcal instead.

**Step 3 – check the rules on each person's plated portion** (not the average): protein, fibre, carbs, added sugar, and protein + veg + healthy fat present. If a rule fails, for example Jade's fibre comes out at 6 g, the card shows a clear note ("Fibre 6 g – target 8 g. Try the extra-veg swap"). Either of you can override.

**Dry vs cooked on the card:**
- **Cooking section:** total dry weight to cook, e.g. "Cook 220 g dry basmati".
- **Plating guide:** cooked weight per person, e.g. "Dale: 190 g cooked rice (≈ 70 g dry) · Jade: 150 g cauliflower rice". There's also a tip: "or weigh the whole pan – Dale gets 64%". That copes with rice absorbing more or less water than the average yield.
- Each item is clearly labelled dry, raw or cooked.

**Starting targets (placeholders until you edit them, not advice):**

| | kcal | Protein | Carbs | Fibre |
|---|---|---|---|---|
| Jade – dinner | 500 | ≥ 35 g | ≤ 45 g | ≥ 8 g |
| Jade – lunch | 450 | ≥ 35 g | ≤ 40 g | ≥ 8 g |
| Dale – dinner | 750 | ≥ 45 g | ~75 g | ≥ 10 g |
| Dale – lunch | 650 | ≥ 40 g | ~60 g | ≥ 8 g |

It's worth Jade checking her numbers with her GP or a dietitian. The app will show a "not medical advice" note.

---

## 5. Decision 4 – rough monthly running cost

| Item | Estimate |
|---|---|
| Hosting (PythonAnywhere free) | £0 |
| AI recipe generation: Claude Opus 5.5 ($4 / $20 per million input / output tokens) is ≈ $0.10 per recipe. About 5 new recipes a week plus a few regenerations of failures is ≈ 25–30 calls a month. Run as an overnight batch (half price), that's ≈ $1.50. | ≈ £1.20 |
| Recipe imports (text or photo), ≈ $0.05 each, a handful a month | ≈ £0.20 |
| Ingredient lookups for unknown ingredients | pennies |
| **Total** | **≈ £1.50–£3 / month** |

Notes:
- Anthropic API usage is **prepaid credit** (the minimum top-up is about $5), so you can't overspend. We'll also set a monthly spend limit in the Anthropic console.
- I've assumed the top model, Opus 5.5. Claude Sonnet 5.5 would be about half the cost, and Haiku 5.5 far cheaper but weaker at precise nutrition rules. **This is your call.** My suggestion is to start on Opus. The library grows each week, so you'll need fewer new recipes over time.

---

## 6. Architecture (plain terms)

```
iPhone / laptop browser  ──HTTPS──▶  Flask app on PythonAnywhere
   (HTML pages + HTMX)                 ├── pages: Menu, Plan, Recipe card, Shopping list, Library, Settings
                                       ├── core logic (plain Python, fully tested):
                                       │     exclusions · nutrition · portions · rules · menu · shopping
                                       ├── SQLite database file
                                       └── Anthropic API calls (key lives only in server .env)
```

The core logic lives in plain Python modules with no web code in them. That keeps them easy to read and test, and the web pages just call them.

Rough folder layout:

```
hormonious/
  app/            Flask routes and HTML templates
  core/           exclusions.py, nutrition.py, portions.py, rules.py, menu.py, shopping.py, ratings.py
  ai/             generate.py, import_recipe.py, prompts
  data/           seed_recipes.json, ingredients.csv (CoFID-derived), pack_sizes.csv
  tests/          pytest tests for every core module
  migrations/     database schema changes (Alembic)
  CLAUDE.md  README.md  .env.example  .gitignore
```

---

## 7. Data model

| Table | Holds |
|---|---|
| `person` | Dale and Jade: name, base-split preference |
| `target` | per person × meal (dinner/lunch): kcal, protein min, carb max or target, fibre min, fat |
| `setting` | nutrition rules, Friday on/off, weekend options, repeat intervals, number of menu options |
| `ingredient` | canonical name, aliases, aisle, nutrition per 100 g (kcal, protein, carbs, sugars, fibre, fat), weighed state (raw/dry/cooked), cooked-yield factor, GI class, flags (refined carb, added sugar, healthy fat, vegetable, protein source), **food families** (e.g. salmon → fish; fish sauce → fish, fish-sauce; mushroom stock → mushroom), pack sizes, data source, verified yes/no |
| `exclusion` | per person: food family or term, plus allowed exceptions (Jade: fish, except fish-sauce / shrimp-paste / breaded-cod) |
| `recipe` | title, source type (AI/imported/seed) + link, servings (4), active and total minutes, tier (weeknight/weekend), steps, reheat note, tags, recipe-level split, status (active/retired) |
| `recipe_item` | recipe ↔ ingredient: grams (plus a friendly quantity and unit, e.g. "2 tbsp"), role **shared-base** or **flexible**, component name (e.g. "carb") |
| `flex_option` | the options for a flexible component: ingredient, default/min/max grams per person, dry or cooked basis, "default" marker |
| `week` / `plan_slot` | the week (starting Saturday) and each night: recipe or "no cook", portions (2 or 4) |
| `portion_choice` | per slot × person × meal: chosen option and any gram override |
| `rating` | recipe × person: stars 1–5, note, date |
| `cook_log` | recipe × date cooked (feeds "last cooked" and repetition) |
| `pantry_staple` | ingredients you always have (hidden from the list by default) |
| `shopping_tick` | week × item: ticked or not |

**Exclusion matching works in two layers.** First by food family, so every ingredient is tagged once and "fish" catches salmon, cod and prawns. Then a keyword safety net on ingredient names and aliases, for anything not yet tagged. Allowed exceptions are checked last. If either of you excludes something, the recipe is never suggested.

---

## 8. Menu, ratings and repetition

- **Menu:** each week the app offers 10–12 weeknight and 3 weekend recipes, drawn from eligible recipes. A recipe is eligible if it passes the exclusions, wasn't cooked last week, and isn't in its rating cooldown. Roughly 60% are favourites (ranked by average rating and how long since you last had them) and 40% are new or untried. Soft preferences ("less spicy", "more veggie nights") gently shift the ranking.
- **Cooldowns from your combined rating** (both editable in settings): 5★ every 2–3 weeks; 4★ every 4–6 weeks; 3★ about every 10 weeks; ≤ 2★ never, unless restored. If you rate a recipe differently, the lower rating wins, since you both have to eat it.

---

## 9. Shopping list

The list is built from the actual per-person grams, including swaps. Then it:
1. converts all quantities to grams or units;
2. merges matching ingredients across the week;
3. rounds up to pack sizes, e.g. "1 × 500 g pack chicken thighs (need 450 g)";
4. groups items by aisle;
5. hides pantry staples behind a "show staples" toggle;
6. lets you tick items off (both phones see the same ticks);
7. offers "Copy as text" for sharing.

---

## 10. AI recipe sources

- **Generate (stage 5):** Claude gets the rules, time limits, exclusions, our ingredient list and the recipe schema, and returns structured JSON. Every recipe then goes through **the same Python validators** as everything else: schema, exclusions, times, per-person rules. A failure is regenerated with the reasons given, up to 2 retries, then discarded. New recipes land in a "New – not yet cooked" pool.
- **Import (stage 6):** paste text or upload a photo or screenshot. Claude pulls out the recipe and suggests which ingredients are flexible. You review and edit everything before saving. **The photo is not stored**, only the extracted recipe, and it stays in your private library.

---

## 11. Phone details

- **Home screen:** Safari → Share → Add to Home Screen. The app opens full-screen with its own icon.
- **Keep screen awake** while cooking: iPhones support this ("Wake Lock") in recent iOS versions. I'll add a "Keep screen on" toggle on the recipe card. If your iOS version doesn't support it, the toggle simply hides.
- Large text and big tap targets on recipe cards and the shopping list.

---

## 12. Build stages

Each stage runs, is committed to git, and ends with "how to run and test it yourself". I stop for your approval after each one.

0. **Set up your PC:** install Python and Git (I'll explain each command first), create the project, connect it to your GitHub (private repository), and add CLAUDE.md, .gitignore and .env.example.
1. **Recipe model and seed library:** database tables, ingredient table (CoFID-derived), food families and exclusion filter, ~20 seed recipes (about 16 weeknight, 4 weekend) with flexible components and swaps. *Tests: exclusions and variants.*
2. **Profiles and planning:** per-person targets, weekly menu generation, picking recipes and assigning nights, no-cook nights, Sunday 4-portion logic. *Tests: rule validation.*
3. **Recipe cards and shopping:** plating guides, nutrition vs target, portion adjustments and swaps, shopping list. *Tests: portions (split, flex, swaps, totals for 4) and shopping merge and rounding.*
4. **Ratings and repetition.** *Tests: cooldown and selection logic.*
5. **AI recipe generation** (needs an Anthropic API account; I'll walk you through it).
6. **Recipe import from text or photo.**
7. **Login, deploy to PythonAnywhere, install on your phones.**
8. *(Optional)* weekly email digest.

README (setup, deployment, environment variables, costs) is started in stage 0 and finished in stage 7.

---

## 13. Out of scope now – worth adding later

- **Freezer stock list:** ties in nicely with "no cook" nights.
- **Tesco online-order helper:** a product search link per item, instead of a full integration.
- **Breakfasts and snacks with a daily overview:** only if Jade finds per-meal targets aren't enough.
- **Batch-cook Sundays** for busy weeks.
- **Offline shopping list:** for patchy supermarket signal.

---

## 14. Confirmed decisions

1. Saturday special = 2 portions; Sunday special = 4 (covers Monday lunch).
2. Week runs Saturday → Friday. The shop arrives Friday or Saturday. The next week's menu is ready each **Monday**.
3. AI features use **Claude Opus 5.5**.
4. The project lives in OneDrive\Documents\Hormonious. The local database is kept out of git.
