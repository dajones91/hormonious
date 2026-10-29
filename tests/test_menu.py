"""Weekly menu building and the shape of a planning week."""

from datetime import date, timedelta

from core.menu import build_menu, check_assignment, menu_is_ready, menu_ready_date, week_slots, week_start_for

SAT = date(2026, 10, 31)


def test_week_start_is_the_saturday_of_the_week_we_are_in():
    assert week_start_for(date(2026, 10, 26)) == date(2026, 10, 24)  # Monday -> last Saturday
    assert week_start_for(date(2026, 10, 30)) == date(2026, 10, 24)  # Friday
    assert week_start_for(SAT) == SAT  # Saturday itself starts a new week
    assert week_start_for(date(2026, 11, 1)) == SAT  # Sunday


def test_menu_is_ready_from_the_monday_before():
    assert not menu_is_ready(SAT, date(2026, 10, 25))  # Sunday before
    assert menu_is_ready(SAT, date(2026, 10, 26))  # Monday
    assert menu_is_ready(SAT, date(2026, 11, 3))  # during the week itself


def test_menu_ready_on_monday_before():
    assert menu_ready_date(SAT) == date(2026, 10, 26)
    assert menu_ready_date(SAT).weekday() == 0


def test_week_slots():
    slots = week_slots(SAT)
    assert [s.day.strftime("%a") for s in slots] == ["Sat", "Sun", "Mon", "Tue", "Wed", "Thu", "Fri"]
    assert [s.kind for s in slots] == ["weekend", "weekend", "weeknight", "weeknight", "weeknight", "weeknight", "off"]
    assert [s.portions for s in slots] == [2, 4, 4, 4, 4, 4, 2]
    sunday = slots[1]
    assert sunday.lunch_for == date(2026, 11, 2)  # Sunday's cook covers Monday lunch
    assert slots[5].lunch_for == date(2026, 11, 6)  # Thursday's cook covers Friday lunch
    assert week_slots(SAT, friday_plan=True)[6].kind == "weeknight"


def test_menu_sizes_and_tiers(recipes):
    menu = build_menu(recipes, SAT, {}, 11, 3)
    by_slug = {r.slug: r for r in recipes}
    assert len(menu.weeknight) == 11 and len(menu.weekend) == 3
    assert all(by_slug[s].tier == "weeknight" for s in menu.weeknight)
    assert all(by_slug[s].tier == "weekend" for s in menu.weekend)
    assert len(set(menu.weeknight)) == 11


def test_nothing_cooked_last_week(recipes):
    last_week = SAT - timedelta(days=3)
    cooked = {r.slug: last_week for r in recipes[:5]}
    menu = build_menu(recipes, SAT, cooked, 20, 5)
    assert not set(cooked) & set(menu.weeknight + menu.weekend)


def test_cooked_two_weeks_ago_can_return(recipes):
    cooked = {recipes[0].slug: SAT - timedelta(days=14)}
    menu = build_menu(recipes, SAT, cooked, 20, 5)
    assert recipes[0].slug in menu.weeknight


def test_longer_since_cooked_ranks_higher(recipes):
    weeknights = [r for r in recipes if r.tier == "weeknight"]
    recent = {r.slug: SAT - timedelta(days=8) for r in weeknights[:8]}  # just outside last week
    menu = build_menu(recipes, SAT, recent, 8, 3)
    never_cooked = {r.slug for r in weeknights[8:]}
    assert len(set(menu.weeknight) & never_cooked) >= 6


def test_same_week_same_menu_different_week_changes(recipes):
    a = build_menu(recipes, SAT, {}, 11, 3)
    assert a == build_menu(recipes, SAT, {}, 11, 3)
    others = [build_menu(recipes, SAT + timedelta(days=7 * k), {}, 11, 3) for k in range(1, 5)]
    assert any(o.weeknight != a.weeknight for o in others)


def test_menu_only_uses_eligible_recipes(recipes):
    eligible = [r for r in recipes if r.slug != "turkey-chilli"]
    menu = build_menu(eligible, SAT, {}, 20, 5)
    assert "turkey-chilli" not in menu.weeknight


def test_assignment_warnings(recipes):
    by_slug = {r.slug: r for r in recipes}
    slots = week_slots(SAT)
    monday, saturday = slots[2], slots[0]
    assert check_assignment(monday, by_slug["turkey-chilli"]) == []
    assert "weekend special" in check_assignment(monday, by_slug["lamb-rogan-josh"])[0]
    assert check_assignment(saturday, by_slug["crispy-cod-chips-peas"]) == []  # 2 portions, no lunch
    sunday = slots[1]
    assert "lunchbox" in check_assignment(sunday, by_slug["crispy-cod-chips-peas"])[0]
