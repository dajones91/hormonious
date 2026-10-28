# Hormonious

A private weekly meal planner for two, designed to support high-protein, low-GI eating in line with PCOS/PMOS-friendly guidance. **Not medical advice.**

See [PLAN.md](PLAN.md) for the design and [CLAUDE.md](CLAUDE.md) for project conventions.

## Local setup (Windows)

Prerequisites: Python 3.13 and Git (installed with `winget install --id Python.Python.3.13 -e` and `winget install --id Git.Git -e`).

```powershell
git clone https://github.com/dajones91/hormonious.git
cd hormonious
python -m venv .venv          # private Python environment for this project
.\.venv\Scripts\Activate.ps1  # switch this terminal to use it
copy .env.example .env        # then edit .env
```

Then install the libraries and build the local database:

```powershell
pip install -r requirements.txt
python manage.py reset-db     # creates hormonious.db from the files in data/
```

## Useful commands

| Command | What it does |
|---|---|
| `python manage.py recipes` | Lists every recipe with time, nutrition per even portion and any rule problems |
| `python manage.py check "oyster sauce"` | Tests the exclusion filter on any ingredient name |
| `python -m pytest` | Runs all the tests |

## Where things live

| Folder | Contents |
|---|---|
| `core/` | The rules in plain Python: recipe schema, food families, exclusions, nutrition |
| `db/` | Database tables and saving/loading |
| `data/` | Editable seed data: `ingredients.csv`, `seed_recipes.json`, `household.json` |
| `tests/` | Automated tests |

Nutrition values in `data/ingredients.csv` are approximate UK figures per 100 g (`source=approx-uk`, `verified=0`). They'll be checked against CoFID before we rely on them for portions.

## Environment variables

Copy `.env.example` to `.env` and fill it in. `.env` is never committed.

| Variable | Purpose |
|---|---|
| `SECRET_KEY` | Signs login cookies |
| `FAMILY_PASSWORD` | Shared login password |
| `ANTHROPIC_API_KEY` | AI recipe generation and import |
| `DATABASE_URL` | Database location (SQLite by default) |

## Deployment

_Filled in during stage 7 (PythonAnywhere)._

## Running costs

Expected ≈ £1.50–£3 a month: free hosting plus Anthropic API usage on prepaid credit. See PLAN.md §5.
