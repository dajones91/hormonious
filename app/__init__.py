"""The Flask web app. Run it with: python manage.py serve (or wsgi.py on the server)."""

import os
from datetime import date, timedelta

from dotenv import load_dotenv
from flask import Flask, flash, g, jsonify, redirect, url_for

from db.models import ENV_FILE, make_session_factory

PLACEHOLDERS = {"", "change-me", "dev-only-change-me"}


def create_app(database_url: str | None = None, today: date | None = None,
               family_password: str | None = None, production: bool = False) -> Flask:
    """Build the app. Settings come from .env unless given here (tests pass them directly).

    `production=True` (used by wsgi.py on the server) refuses to start without a real
    SECRET_KEY and FAMILY_PASSWORD, and only sends the login cookie over https.
    """
    load_dotenv(ENV_FILE)
    app = Flask(__name__)
    secret = os.getenv("SECRET_KEY", "")
    password = family_password if family_password is not None else os.getenv("FAMILY_PASSWORD", "")
    if production and (secret in PLACEHOLDERS or password in PLACEHOLDERS):
        raise RuntimeError("Set a real SECRET_KEY and FAMILY_PASSWORD in .env before running online.")
    app.config.update(
        SECRET_KEY=secret if secret not in PLACEHOLDERS else "dev-only-not-secret",
        FAMILY_PASSWORD=password if password not in PLACEHOLDERS else None,  # None = login switched off
        PERMANENT_SESSION_LIFETIME=timedelta(days=180),  # stay logged in on your phones
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",  # other sites can't submit our forms with our cookie
        SESSION_COOKIE_SECURE=production,
        SESSION_FACTORY=make_session_factory(database_url),
        TODAY=today,  # tests can pin the date; None means the real date
        MAX_CONTENT_LENGTH=15 * 1024 * 1024,  # photo uploads up to 15 MB
    )

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

    @app.route("/manifest.webmanifest", endpoint="manifest")
    def manifest():
        """Tells phones how to install the app: name, icons, colours, and open full-screen."""
        icons = [{"src": url_for("static", filename=f"icons/icon-{n}.png"), "sizes": f"{n}x{n}", "type": "image/png"}
                 for n in (192, 512)]
        response = jsonify(name="Hormonious", short_name="Hormonious", start_url="/", scope="/",
                           display="standalone", background_color="#faf6f0", theme_color="#9a6b4b", icons=icons)
        response.mimetype = "application/manifest+json"
        return response

    from core.ratings import stars_text
    app.add_template_global(stars_text)

    from app import auth
    app.before_request(auth.require_login)
    app.register_blueprint(auth.bp)

    @app.context_processor
    def who_am_i():
        return {"me": auth.current_person(), "login_enabled": auth.login_enabled()}

    from app.views import bp
    app.register_blueprint(bp)
    return app
