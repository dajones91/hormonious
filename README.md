# Hormonious

A private weekly meal planner for two, designed to support high-protein, low-GI eating in line with PCOS/PMOS-friendly guidance. **Not medical advice.**

See [PLAN.md](PLAN.md) for the design and [CLAUDE.md](CLAUDE.md) for project conventions.

## Local setup (Windows)

Prerequisites: Python 3.13 and Git (installed with `winget install --id Python.Python.3.13 -e` and `winget install --id Git.Git -e`).

```powershell
git clone https://github.com/dajones91/hormonious.git
cd hormonious
python -m venv .venv          # private Python environment for this project
copy .env.example .env        # then edit .env
```

Every command below runs the project's own Python directly (`.\.venv\Scripts\python.exe`), so there's
no "activate" step and no need to change Windows' script settings.

Install the libraries and build the local database:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe manage.py reset-db     # creates hormonious.db from the files in data/
```

## Useful commands

| Command | What it does |
|---|---|
| `.\.venv\Scripts\python.exe manage.py serve` | Runs the app at http://127.0.0.1:5000 (this PC only, with the debugger on) |
| `.\.venv\Scripts\python.exe manage.py serve --lan` | Also lets phones on your home Wi-Fi open it at `http://<this PC's IP>:5000` (debugger off) |
| `.\.venv\Scripts\python.exe manage.py recipes` | Lists every recipe with Dale's and Jade's dinner plates and any rule problems |
| `.\.venv\Scripts\python.exe manage.py check "oyster sauce"` | Tests the exclusion filter on any ingredient name |
| `.\.venv\Scripts\python.exe -m pytest` | Runs all the tests |
| `.\.venv\Scripts\python.exe manage.py generate --tier weeknight --idea "a lamb curry"` | Creates a new AI recipe (needs `ANTHROPIC_API_KEY`; about 10–30p each) |

## Where things live

| Folder | Contents |
|---|---|
| `core/` | The rules in plain Python: recipe schema, food families, exclusions, nutrition, portions, rules, menu |
| `db/` | Database tables, saving/loading, and `planner.py` which ties the rules to the database |
| `app/` | The Flask web app: pages (`views.py`), HTML templates and CSS |
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

Step-by-step guide: [docs/DEPLOY.md](docs/DEPLOY.md). In short: a free PythonAnywhere account, the code cloned from GitHub with a read-only token, secrets in `.env`, your database uploaded, a manual-config web app pointing at `wsgi.py`, Force HTTPS on, then Safari → Add to Home Screen on each iPhone.

`wsgi.py` refuses to start without a real `SECRET_KEY` and `FAMILY_PASSWORD`. Database structure changes are Alembic migrations (`migrations/versions`) that run automatically when the app starts.

## Running costs

Expected ≈ £1.50–£3 a month: free hosting plus Anthropic API usage on prepaid credit. See PLAN.md §5.
