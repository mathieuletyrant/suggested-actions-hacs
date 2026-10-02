"""Counting, forgetting and ranking, as pure functions.

**Never imports homeassistant** -- that is the point of the file, and what lets
the arithmetic be tested without a running instance. `__init__.py` is what
turns a service call into the arguments these take.
"""

from __future__ import annotations

from collections import deque
from collections.abc import Iterable, Mapping

DAYS = 7
HOURS = 24

# Fixed rather than options: nobody tuning their install could say what 0.4
# instead of 0.5 would change, and a wrong value silently ruins the ranking.
# Expose them the day someone shows a habit these get wrong.
NEIGHBOUR_WEIGHT = 0.5
EVERY_DAY_WEIGHT = 0.2

# A script's own service is the script: `script.arrosage` called as
# `script.arrosage()` targets no entity, so the entity is the service name.
# These four are the generic ones, which name their target in entity_id.
SCRIPT_BUILTINS = frozenset({"turn_on", "turn_off", "toggle", "reload"})

NO_USER = "no_user"
USER_NOT_FOLLOWED = "user_not_followed"
SAME_CLICK = "same_click"
DUPLICATE = "duplicate"


def empty_usage() -> dict:
    """What a freshly added action stores: nothing counted yet."""
    grid = [[0.0] * HOURS for _ in range(DAYS)]
    return {"grid": grid, "updated": 0.0, "last_used": 0.0}


def entities_of_call(domain: str, service: str, data: Mapping) -> set[str]:
    """The entity ids a service call is aimed at.

    Device and area targets are not expanded: a dashboard button names its
    entity, which is the click this listens for.
    """
    raw = data.get("entity_id", [])
    if isinstance(raw, str):
        raw = raw.split(",")
    found = {entity_id.strip() for entity_id in raw if entity_id.strip()}
    if domain == "script" and service not in SCRIPT_BUILTINS:
        found.add(f"script.{service}")
    return found


def _forgetting(usage: Mapping, now: float, half_life: float) -> float:
    """How much of what was counted still counts at `now`.

    Applied on read rather than by a timer, from the moment the grid was last
    written: an action left alone fades whether or not anything else is used.
    """
    if not usage["updated"]:
        return 1.0
    return 0.5 ** (max(now - usage["updated"], 0.0) / half_life)


def record(usage: dict, now: float, weekday: int, hour: int, half_life: float) -> None:
    """Count one use in the weekday x hour slot, after forgetting what is due."""
    factor = _forgetting(usage, now, half_life)
    grid = [[count * factor for count in row] for row in usage["grid"]]
    grid[weekday][hour] += 1
    usage.update(grid=grid, updated=now, last_used=now)


def score(
    usage: Mapping, now: float, weekday: int, hour: int, half_life: float
) -> float:
    """How likely the action is now: this weekday's habit, plus a fifth of
    every day's, each smoothed over the neighbouring hours.

    The every-day term is what lets a daily habit show on a Tuesday it was
    never used on. Hours wrap at midnight within the same row.
    """

    def smoothed(row: list[float]) -> float:
        return row[hour] + NEIGHBOUR_WEIGHT * (row[hour - 1] + row[(hour + 1) % HOURS])

    grid = usage["grid"]
    every_day = sum(smoothed(row) for row in grid)
    raw = smoothed(grid[weekday]) + EVERY_DAY_WEIGHT * every_day
    return raw * _forgetting(usage, now, half_life)


def rank(scored: Iterable[tuple[str, float, float]]) -> list[tuple[str, float]]:
    """(action, score, last_used) sorted best first; a tie goes to the most
    recently used.
    """
    ordered = sorted(scored, key=lambda item: (item[1], item[2]), reverse=True)
    return [(action, value) for action, value, _ in ordered]


def top(ranking: list[tuple[str, float]], size: int, threshold: float) -> list[str]:
    """The suggestions: the first `size` actions that reach the threshold."""
    return [action for action, value in ranking if value >= threshold][:size]


def admit(
    actions: list[str],
    context_id: str,
    seen: deque,
    last_used: Mapping[str, float],
    now: float,
    window: float,
) -> tuple[list[str], str | None]:
    """Which of the actions a call touches count as a use, or why none does.

    One click is one use. A script called from the dashboard runs its own
    service calls under the click's context, so the terrace script switching on
    L1 must not count L1 as well. The context is remembered *before* the
    duplicate check: if the script itself is a duplicate, its inner calls must
    still be recognised as the same click rather than counted as fresh ones.
    """
    if context_id in seen:
        return [], SAME_CLICK
    seen.append(context_id)
    fresh = [action for action in actions if now - last_used.get(action, 0.0) >= window]
    if not fresh:
        return [], DUPLICATE
    return fresh, None
