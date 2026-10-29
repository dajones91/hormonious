"""Ratings, cooldowns and how ratings shape the weekly menu."""

from collections import Counter
from datetime import date, timedelta

import pytest

from core.menu import build_menu
from core.ratings import Rating, available_from, cooldown_weeks, household_rating, is_retired, stars_text

SAT = date(2026, 10, 31)
MON = date(2026, 11, 2)


# --- Household rating ----------------------------------------------------------------

def test_lower_of_the_two_ratings_counts():
    assert household_rating([Rating("dale", 5, MON), Rating("jade", 3, MON)]) == 3


def test_one_rating_counts_on_its_own():
    assert household_rating([Rating("jade", 4, MON)]) == 4


def test_no_ratings_is_none_not_zero():
    assert household_rating([]) is None
    assert not is_retired(None)


def test_latest_rating_per_person_wins():
    ratings = [Rating("dale", 2, MON), Rating("jade", 5, MON), Rating("dale", 5, MON + timedelta(days=21))]
    assert household_rating(ratings) == 5


def test_restore_ignores_older_ratings():
    ratings = [Rating("dale", 1, MON), Rating("jade", 2, MON)]
    assert is_retired(household_rating(ratings))
    assert household_rating(ratings, restored_on=MON + timedelta(days=1)) is None
    newer = ratings + [Rating("jade", 4, MON + timedelta(days=30))]
    assert household_rating(newer, restored_on=MON + timedelta(days=1)) == 4


def test_stars_text():
    assert stars_text(4) == "★★★★☆" and stars_text(None) == "Not rated yet"


# --- Cooldowns -----------------------------------------------------------------------------

@pytest.mark.parametrize("stars, weeks", [(5, 2), (4, 4), (3, 10), (None, 2), (2, None), (1, None)])
def test_cooldown_weeks(stars, weeks):
    assert cooldown_weeks(stars) == weeks


def test_available_from_counts_whole_weeks_from_the_week_we_had_it():
    # cooked Monday 2 Nov, in the week starting Sat 31 Oct
    assert available_from(MON, 5) == SAT + timedelta(weeks=2)  # back from Sat 14 Nov
    assert available_from(MON, 4) == SAT + timedelta(weeks=4)
    assert available_from(MON, 3) == SAT + timedelta(weeks=10)
    assert available_from(MON, None) == SAT + timedelta(weeks=2)  # forgot to rate: just "not next week"
    assert available_from(MON, 2) is None
    assert available_from(None, 4) == date.min  # never cooked: any time


# --- The menu ------------------------------------------------------------------------------

def weeknights(recipes):
    return [r for r in recipes if r.tier == "weeknight"]


def test_retired_recipes_never_offered(recipes):
    slug = weeknights(recipes)[0].slug
    menu = build_menu(recipes, SAT, {}, 20, 5, stars={slug: 2})
    assert slug not in menu.weeknight


def test_cooldowns_respected(recipes):
    a, b, c = (r.slug for r in weeknights(recipes)[:3])
    cooked = {a: SAT - timedelta(days=12), b: SAT - timedelta(days=12), c: SAT - timedelta(days=12)}  # 2 weeks ago
    menu = build_menu(recipes, SAT, cooked, 20, 5, stars={a: 5, b: 4, c: None})
    assert a in menu.weeknight  # 5 stars: back after 2 weeks
    assert b not in menu.weeknight  # 4 stars: needs 4 weeks
    assert c in menu.weeknight  # not rated: neutral, back after 2 weeks


def test_forgetting_to_rate_is_not_a_penalty(recipes):
    """A cooked-but-unrated recipe isn't treated like a 3-star or retired one."""
    wn = weeknights(recipes)
    cooked = {r.slug: SAT - timedelta(weeks=3) for r in wn}
    unrated, three = wn[0].slug, wn[1].slug
    stars = {three: 3}
    picks = Counter()
    for k in range(20):
        start = SAT + timedelta(weeks=k * 20)  # far apart, so cooldowns don't interfere
        menu = build_menu(recipes, start, cooked, 6, 2, stars=stars)
        picks.update(menu.weeknight)
    assert picks[unrated] > picks[three]


def test_favourites_take_about_60_percent(recipes):
    wn = weeknights(recipes)
    stars = {r.slug: 5 for r in wn[:8]}  # 8 favourites, 8 untried
    menu = build_menu(recipes, SAT, {}, 10, 3, stars=stars)
    favs = sum(1 for s in menu.weeknight if s in stars)
    assert favs == 6 and len(menu.weeknight) == 10


def test_short_group_is_topped_up(recipes):
    wn = weeknights(recipes)
    stars = {wn[0].slug: 5}  # only one favourite
    menu = build_menu(recipes, SAT, {}, 10, 3, stars=stars)
    assert len(menu.weeknight) == 10 and wn[0].slug in menu.weeknight


def test_favourites_come_back_more_often_over_time(recipes):
    """Simulate 16 weeks: we cook the top 4 weeknight options each week. 5-star recipes
    should turn up more often than 3-star ones, and never two weeks running."""
    wn = weeknights(recipes)
    stars = {r.slug: 5 for r in wn[:4]} | {r.slug: 3 for r in wn[4:8]}
    last: dict[str, date] = {}
    cooked = Counter()
    previous: set[str] = set()
    for k in range(16):
        start = SAT + timedelta(weeks=k)
        menu = build_menu(recipes, start, dict(last), 11, 3, stars=stars)
        this_week = menu.weeknight[:4]
        assert not previous & set(this_week)  # nothing from last week
        for i, slug in enumerate(this_week):
            last[slug] = start + timedelta(days=2 + i)
        cooked.update(this_week)
        previous = set(this_week)
    five = sum(cooked[r.slug] for r in wn[:4]) / 4
    three = sum(cooked[r.slug] for r in wn[4:8]) / 4
    assert five >= 4 and three <= 2 and five > three


def test_restore_on_the_same_day_as_the_rating():
    assert household_rating([Rating("jade", 1, MON)], restored_on=MON) is None
