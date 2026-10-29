"""The weekly menu and the shape of a planning week.

A week runs Saturday to Friday (the shop arrives Friday or Saturday). The
menu for the coming week is ready from the Monday before.
"""

import random
from dataclasses import dataclass
from datetime import date, timedelta

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
               n_weeknight: int, n_weekend: int) -> Menu:
    """Pick this week's options from recipes that already pass exclusions and rules.

    Anything cooked in the 7 days before the week starts is left out. The rest
    are ranked by how long it's been since we had them, plus a little
    randomness so the menu changes week to week. The same week always gets
    the same menu. (Ratings and favourites are added in stage 4.)
    """
    rng = random.Random(week_start.toordinal())
    cutoff = week_start - timedelta(days=7)

    def score(r: Recipe) -> float:
        last = last_cooked.get(r.slug)
        days_since = 60 if last is None else min((week_start - last).days, 60)
        return days_since + rng.uniform(0, 30)

    def pick(tier: str, n: int) -> list[str]:
        pool = [r for r in eligible if r.tier == tier
                and not (r.slug in last_cooked and last_cooked[r.slug] >= cutoff)]
        pool.sort(key=lambda r: (score(r), r.slug), reverse=True)
        return [r.slug for r in pool[:n]]

    return Menu(pick("weeknight", n_weeknight), pick("weekend", n_weekend))


def check_assignment(slot: DaySlot, recipe: Recipe) -> list[str]:
    """Warnings when a recipe is put on a night it doesn't suit."""
    warnings = []
    if slot.kind == "weeknight" and recipe.tier != "weeknight":
        warnings.append(f"{recipe.title} is a weekend special ({recipe.total_min} min) on a weeknight")
    if slot.portions == 4 and "lunchbox-friendly" not in recipe.tags:
        warnings.append(f"{recipe.title} isn't lunchbox-friendly, but {slot.label} also makes tomorrow's lunch")
    return warnings
