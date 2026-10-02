"""The arithmetic and the click rules, without Home Assistant."""

from collections import deque

import pytest

from custom_components.suggested_actions import habits
from custom_components.suggested_actions.const import DEFAULTS, OPTION_THRESHOLD

DAY = 86400
HALF_LIFE = 14 * DAY
SATURDAY, MONDAY = 5, 0
THRESHOLD = DEFAULTS[OPTION_THRESHOLD]


def used(*slots, every=7 * DAY, start=0.0):
    """An action used at each (weekday, hour), one per `every` seconds."""
    usage = habits.empty_usage()
    now = start
    for weekday, hour in slots:
        now += every
        habits.record(usage, now, weekday, hour, HALF_LIFE)
    return usage, now


def test_a_script_called_by_its_own_service_is_the_script():
    assert habits.entities_of_call("script", "arrosage", {}) == {"script.arrosage"}


def test_script_turn_on_names_its_target():
    found = habits.entities_of_call("script", "turn_on", {"entity_id": "script.a"})
    assert found == {"script.a"}


def test_entity_ids_come_as_string_list_or_comma_list():
    for given in (["a.b", "c.d"], "a.b, c.d"):
        found = habits.entities_of_call("light", "turn_on", {"entity_id": given})
        assert found == {"a.b", "c.d"}


def test_one_use_halves_after_one_half_life():
    usage, now = used((MONDAY, 8))
    fresh = habits.score(usage, now, MONDAY, 8, HALF_LIFE)
    later = habits.score(usage, now + HALF_LIFE, MONDAY, 8, HALF_LIFE)
    assert later == pytest.approx(fresh / 2)


def test_a_single_click_never_reaches_the_default_threshold():
    """The one-off Tuesday air conditioning must not make the list, not even
    in the minutes right after the click.
    """
    usage, now = used((MONDAY, 15))
    assert habits.score(usage, now, MONDAY, 15, HALF_LIFE) < THRESHOLD


def test_a_saturday_habit_is_suggested_on_saturday_and_not_on_monday():
    usage, now = used(*[(SATURDAY, 10)] * 2)
    assert habits.score(usage, now + 7 * DAY, SATURDAY, 10, HALF_LIFE) >= THRESHOLD
    assert habits.score(usage, now + 2 * DAY, MONDAY, 10, HALF_LIFE) < THRESHOLD


def test_a_daily_habit_is_suggested_within_a_week():
    usage, now = used(*[(day % 7, 20) for day in range(7)], every=DAY)
    assert habits.score(usage, now + DAY, 0, 20, HALF_LIFE) >= THRESHOLD


def test_neighbouring_hours_count_half_and_wrap_at_midnight():
    usage, now = used((MONDAY, 0))
    on_the_hour = habits.score(usage, now, MONDAY, 0, HALF_LIFE)
    next_to_it = habits.score(usage, now, MONDAY, 23, HALF_LIFE)
    assert next_to_it == pytest.approx(on_the_hour / 2)


def test_a_tie_goes_to_the_most_recently_used():
    scored = [("old", 2.0, 10.0), ("new", 2.0, 20.0), ("best", 3.0, 0.0)]
    assert habits.rank(scored) == [("best", 3.0), ("new", 2.0), ("old", 2.0)]


def test_top_keeps_only_what_reaches_the_threshold_up_to_the_size():
    ranking = [("a", 5.0), ("b", 4.0), ("c", 3.0), ("d", 1.0)]
    assert habits.top(ranking, 2, 1.5) == ["a", "b"]
    assert habits.top(ranking, 5, 3.5) == ["a", "b"]


def test_a_script_switching_on_another_tracked_entity_counts_once():
    """The terrace script turns L1 on under the click's context."""
    seen = deque(maxlen=64)
    counted, reason = habits.admit(["prise_terrasse"], "click", seen, {}, 1000, 300)
    assert (counted, reason) == (["prise_terrasse"], None)
    counted, reason = habits.admit(["l1_exterieur"], "click", seen, {}, 1000, 300)
    assert (counted, reason) == ([], habits.SAME_CLICK)


def test_a_duplicate_click_still_hides_its_inner_calls():
    """If the script is a duplicate, L1 behind it is not a fresh use either."""
    seen = deque(maxlen=64)
    last = {"prise_terrasse": 900}
    assert habits.admit(["prise_terrasse"], "again", seen, last, 1000, 300) == (
        [],
        habits.DUPLICATE,
    )
    assert habits.admit(["l1_exterieur"], "again", seen, {}, 1000, 300) == (
        [],
        habits.SAME_CLICK,
    )


def test_a_click_after_the_window_counts():
    seen = deque(maxlen=64)
    last = {"clim": 1000}
    assert habits.admit(["clim"], "later", seen, last, 1300, 300) == (["clim"], None)
