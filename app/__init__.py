"""The Flask web app. Run it with: python manage.py serve"""

import os
from datetime import date

from flask import Flask, g

from db.models import make_session_factory


def create_app(database_url: str | None = None, today: date | None = None) -> Flask:
    app = Flask(__name__)
    app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "dev-only-change-me")
    app.config["SESSION_FACTORY"] = make_session_factory(database_url)
    app.config["TODAY"] = today  # tests can pin the date; None means the real date

    @app.teardown_appcontext
    def close_db(exc):
        db = g.pop("db", None)
        if db is not None:
            db.close()

    @app.template_global()
    def cuisine_hue(name: str) -> int:
        """A stable colour per cuisine for the placeholder images, kept in the blue/teal/violet range."""
        return 190 + sum(map(ord, name)) % 80

    from app.views import bp
    app.register_blueprint(bp)
    return app
