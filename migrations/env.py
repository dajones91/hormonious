"""Alembic setup: how database migrations connect to our database.

Normally migrations run automatically when the app starts (db/models.upgrade_database),
which hands over its own connection. Running `alembic` by hand uses DATABASE_URL from .env.
"""

from alembic import context
from sqlalchemy import create_engine

from db.models import Base, database_url

target_metadata = Base.metadata


def run_migrations(connection) -> None:
    # render_as_batch lets SQLite change existing tables (it can't ALTER most things in place)
    context.configure(connection=connection, target_metadata=target_metadata, render_as_batch=True)
    with context.begin_transaction():
        context.run_migrations()


connection = context.config.attributes.get("connection")
if connection is not None:
    run_migrations(connection)
else:
    with create_engine(database_url()).connect() as conn:
        run_migrations(conn)
        conn.commit()
