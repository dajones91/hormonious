"""The Flask web app. Run it with: python manage.py serve"""

import os
from datetime import date

from flask import Flask, flash, g, redirect, url_for

from db.models import make_session_factory


def create_app(database_url: str | None = None, today: date | None = None) -> Flask:
    app = Flask(__name__)
    app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "dev-only-change-me")
    app.config["SESSION_FACTORY"] = make_session_factory(database_url)
    app.config["TODAY"] = today  # tests can pin the date; None means the real date
    app.config["MAX_CONTENT_LENGTH"] = 15 * 1024 * 1024  # photo uploads up to 15 MB

    @app.errorhandler(413)
    def too_big(exc):
        flash("That photo is too big (over 15 MB). Try a screenshot instead.", "error")
        return redirect(url_for("main.recipes"))

    @app.teardown_appcontext
    def close_db(exc):
        db = g.pop("db", None)
        if db is not None:
            db.close()

    @app.template_global()
    def cuisine_hue(name: str) -> int:
        """A stable colour per cuisine for the placeholder images, kept in warm browns, ambers and greens."""
        return (15 + sum(map(ord, name)) % 85) % 360  # 15-100: chocolate, amber, olive, sage

    from core.ratings import stars_text
    app.add_template_global(stars_text)

    from app.views import bp
    app.register_blueprint(bp)
    return app
