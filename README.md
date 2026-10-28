# Hormonious

A private weekly meal planner for two, designed to support high-protein, low-GI eating in line with PCOS/PMOS-friendly guidance. **Not medical advice.**

See [PLAN.md](PLAN.md) for the design and [CLAUDE.md](CLAUDE.md) for project conventions.

## Local setup (Windows)

_Filled in during stage 0–1._

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
