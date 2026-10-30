"""The weekly menu and the shape of a planning week.

A week runs Saturday to Friday (the shop arrives Friday or Saturday). The
menu for the coming week is ready from the Monday before.
"""

import random
from dataclasses import dataclass
from datetime import date, timedelta

from core.ratings import DEFAULT_COOLDOWN_WEEKS, available_from
from core.schema import Recipe

SATURDAY = 5  # date.weekday(): Monday is 0


def week_start_for(today: date) -> date:
    """The Saturday that starts the week we're in (today, if it's Saturday)."""
    return today - timedelta(days=(today.weekday() - SATURDAY) % 7)


def menu_ready_date(week_start: date) -> date:
    """The Monday before the week starts: the day its menu is built and can be planned."""
    return week_start - timedelta(days=5)


def menu_is_ready(week_start: date, today: date) -> bool:
    return today >= menu_ready_date(week_start)


@dataclass(frozen=True)
class DaySlot:
    day: date
    kind: str  # "weekend", "weeknight" or "off"
    portions: int  # 4 = dinner + next-day lunch, 2 = dinner only
    lunch_for: date | None  # the day the extra portions are eaten as lunch

    @property
    def label(self) -> str:
        return self.day.strftime("%a %d %b")


def week_slots(week_start: date, friday_plan: bool = False) -> list[DaySlot]:
    """Sat (2 portions), Sun (4, covers Monday lunch), Mon-Thu (4 each), Fri (off by default)."""
    slots = []
    for offset in range(7):
        day = week_start + timedelta(days=offset)
        wd = day.weekday()
        if wd == 5:
            slots.append(DaySlot(day, "weekend", 2, None))
        elif wd == 6:
            slots.append(DaySlot(day, "weekend", 4, day + timedelta(days=1)))
        elif wd <= 3:
            slots.append(DaySlot(day, "weeknight", 4, day + timedelta(days=1)))
        else:  # Friday
            slots.append(DaySlot(day, "weeknight" if friday_plan else "off", 2, None))
    return slots


@dataclass(frozen=True)
class Menu:
    weeknight: list[str]
    weekend: list[str]


def build_menu(eligible: list[Recipe], week_start: date, last_cooked: dict[str, date],
               n_weeknight: int, n_weekend: int, stars: dict[str, int | None] | None = None,
               cooldowns: dict[int, int] = DEFAULT_COOLDOWN_WEEKS, favourite_share: float = 0.6) -> Menu:
    """Pick this week's options from recipes that already pass exclusions and rules.

    1. Leave out anything retired (2 stars or less) or still in its cooldown (see
       core/ratings.py). That always includes anything we had last week.
    2. Favourites (4-5 stars) fill about 60% of the places, the most overdue first,
       so 5-star recipes come back more often than 4-star ones.
    3. The rest go to recipes we haven't tried or haven't rated, then 3-star ones,
       with some randomness so the menu changes week to week.
    If either group runs short, the other fills the gap. The same week always gets
    the same menu.
    """
    stars = stars or {}
    rng = random.Random(week_start.toordinal())

    def opens(r: Recipe) -> date | None:
        return available_from(last_cooked.get(r.slug), stars.get(r.slug), cooldowns)

    def weeks_overdue(r: Recipe) -> float:
        return min((week_start - opens(r)).days / 7, 12)  # never cooked counts as 12

    def favourite_score(r: Recipe) -> float:
        return weeks_overdue(r) + stars[r.slug] - 4 + rng.uniform(0, 1.5)

    def other_score(r: Recipe) -> float:
        score = min(weeks_overdue(r), 8) + rng.uniform(0, 10)
        if r.slug not in last_cooked:
            score += 3  # never tried: give new recipes a fair chance
        if stars.get(r.slug) == 3:
            score -= 6  # 3 stars: only now and then
        return score

    def pick(tier: str, n: int) -> list[str]:
        pool = [r for r in eligible if r.tier == tier and opens(r) is not None and opens(r) <= week_start]
        favourites = sorted((r for r in pool if (stars.get(r.slug) or 0) >= 4),
                            key=lambda r: (favourite_score(r), r.slug), reverse=True)
        others = sorted((r for r in pool if (stars.get(r.slug) or 0) < 4),
                        key=lambda r: (other_score(r), r.slug), reverse=True)
        want = round(n * favourite_share)
        chosen = favourites[:want] + others[:n - min(want, len(favourites))]
        chosen += [r for r in favourites[want:] + others if r not in chosen][:n - len(chosen)]
        return [r.slug for r in chosen[:n]]

    return Menu(pick("weeknight", n_weeknight), pick("weekend", n_weekend))


def check_assignment(slot: DaySlot, recipe: Recipe, has_lunch: bool | None = None) -> list[str]:
    """Warnings when a recipe is put on a night it doesn't suit. `has_lunch`: is anyone boxing a lunch?"""
    has_lunch = slot.portions == 4 if has_lunch is None else has_lunch
    warnings = []
    if slot.kind == "weeknight" and recipe.tier != "weeknight":
        warnings.append(f"{recipe.title} is a weekend special ({recipe.total_min} min) on a weeknight")
    if has_lunch and "lunchbox-friendly" not in recipe.tags:
        warnings.append(f"{recipe.title} isn't lunchbox-friendly, but {slot.label} also makes tomorrow's lunch")
    return warnings
