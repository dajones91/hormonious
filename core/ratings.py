"""Ratings and how often a recipe can come back.

Each of us rates a recipe 1-5 after cooking it. The *household* rating is the
lower of our two latest ratings (we both have to eat it), or the only one if just
one of us has rated it. That rating sets how many weeks must pass before it can be
offered again, counted from the (Saturday-to-Friday) week we last had it:

    5 stars: 2 weeks later   (never next week, so favourites come back every 2-3 weeks)
    4 stars: 4 weeks later   (about every 4-6 weeks)
    3 stars: 10 weeks later  (rarely)
    2 stars or less: never, unless we restore it
    not rated yet: 2 weeks later (just the "nothing from last week" rule)

Restoring a recipe wipes the slate: ratings up to and including the restore day are ignored.
"""

from dataclasses import dataclass
from datetime import date, timedelta

DEFAULT_COOLDOWN_WEEKS = {5: 2, 4: 4, 3: 10}
UNRATED_WEEKS = 2  # never in the week straight after we had it
RETIRE_AT_OR_BELOW = 2


@dataclass(frozen=True)
class Rating:
    person: str
    stars: int
    on: date
    note: str = ""


def household_rating(ratings: list[Rating], restored_on: date | None = None) -> int | None:
    """The lower of each person's most recent rating since any restore, or None if unrated."""
    latest: dict[str, Rating] = {}
    for r in sorted(ratings, key=lambda r: r.on):
        if restored_on is None or r.on > restored_on:  # ratings up to the restore day are ignored
            latest[r.person] = r
    return min(r.stars for r in latest.values()) if latest else None


def is_retired(stars: int | None) -> bool:
    return stars is not None and stars <= RETIRE_AT_OR_BELOW


def cooldown_weeks(stars: int | None, cooldowns: dict[int, int] = DEFAULT_COOLDOWN_WEEKS) -> int | None:
    """Weeks after the week we last had it before it can return. None means never (retired)."""
    if stars is None:
        return UNRATED_WEEKS
    if is_retired(stars):
        return None
    return max(cooldowns.get(stars, UNRATED_WEEKS), UNRATED_WEEKS)


def _week_of(day: date) -> date:
    """The Saturday that starts the week containing `day`."""
    return day - timedelta(days=(day.weekday() - 5) % 7)


def available_from(last: date | None, stars: int | None,
                   cooldowns: dict[int, int] = DEFAULT_COOLDOWN_WEEKS) -> date | None:
    """The first week (its Saturday) a recipe may appear on a menu. None means never."""
    weeks = cooldown_weeks(stars, cooldowns)
    if weeks is None:
        return None
    if last is None:
        return date.min
    return _week_of(last) + timedelta(weeks=weeks)


def stars_text(stars: int | None) -> str:
    return "Not rated yet" if stars is None else "★" * stars + "☆" * (5 - stars)
