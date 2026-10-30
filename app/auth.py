"""Family login: one shared password, then each device says who it is (Dale or Jade).

- The password lives only in .env (FAMILY_PASSWORD) and is compared in constant time.
- After logging in, the device stays signed in for about six months (a signed cookie).
- Too many wrong passwords from one address locks it out for 15 minutes.
- Login is switched off when no real password is configured, which keeps local
  development and the tests simple. The production entry point (wsgi.py) refuses to
  start without one.
"""

import hmac
import time
from collections import defaultdict

from flask import Blueprint, current_app, flash, redirect, render_template, request, session, url_for

from core.portions import PEOPLE

bp = Blueprint("auth", __name__)

MAX_FAILURES = 10
LOCKOUT_SECONDS = 15 * 60
_failures: dict[str, list[float]] = defaultdict(list)  # address -> times of recent wrong passwords

# Pages anyone can reach without logging in.
PUBLIC_ENDPOINTS = {"auth.login", "static", "manifest"}


def login_enabled() -> bool:
    return bool(current_app.config.get("FAMILY_PASSWORD"))


def current_person() -> str | None:
    """Who's using this device: 'dale', 'jade', or None if login is off or not chosen yet."""
    person = session.get("person")
    return person if person in PEOPLE else None


def _locked_out(address: str) -> bool:
    recent = [t for t in _failures[address] if time.time() - t < LOCKOUT_SECONDS]
    _failures[address] = recent
    return len(recent) >= MAX_FAILURES


def require_login():
    """Runs before every page: send anyone not logged in to the login page, then to 'who are you'."""
    if not login_enabled() or request.endpoint in PUBLIC_ENDPOINTS:
        return None
    if not session.get("logged_in"):
        return redirect(url_for("auth.login", next=request.full_path if request.method == "GET" else None))
    if current_person() is None and request.endpoint != "auth.who":
        return redirect(url_for("auth.who", next=request.full_path if request.method == "GET" else None))
    return None


def _safe_next(target: str | None) -> str:
    """Only redirect back to our own pages."""
    if target and target.startswith("/") and not target.startswith("//"):
        return target
    return url_for("main.week")


@bp.route("/login", methods=["GET", "POST"])
def login():
    if not login_enabled():
        return redirect(url_for("main.week"))
    if request.method == "POST":
        address = request.remote_addr or "?"
        if _locked_out(address):
            flash("Too many wrong passwords. Please wait 15 minutes and try again.", "error")
            return render_template("login.html"), 429
        given = request.form.get("password", "")
        if hmac.compare_digest(given.encode(), current_app.config["FAMILY_PASSWORD"].encode()):
            _failures.pop(address, None)
            session.clear()
            session.permanent = True
            session["logged_in"] = True
            return redirect(url_for("auth.who", next=_safe_next(request.args.get("next"))))
        _failures[address].append(time.time())
        flash("That's not the right password.", "error")
    return render_template("login.html")


@bp.route("/who", methods=["GET", "POST"])
def who():
    """Pick who's using this device. Remembered until you switch or log out."""
    if request.method == "POST":
        person = request.form.get("person")
        if person in PEOPLE:
            session["person"] = person
            return redirect(_safe_next(request.args.get("next")))
    return render_template("who.html", people=PEOPLE, current=current_person())


@bp.route("/logout", methods=["POST"])
def logout():
    session.clear()
    return redirect(url_for("auth.login"))
