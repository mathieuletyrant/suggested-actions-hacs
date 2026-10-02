"""The names the flows, the sensor and the entry point share.

Separate from `__init__.py` so that `config_flow.py` can import them without
pulling the listener and the store into its import path.
"""

from __future__ import annotations

DOMAIN = "suggested_actions"

# One subentry per action: Home Assistant's own Add button, row and delete,
# instead of a list editor inside the options.
SUBENTRY_ACTION = "action"
CONF_ACTION_ID = "action_id"
CONF_ENTITIES = "entities"
CONF_ICON = "icon"

OPTION_TOP_SIZE = "top_size"
OPTION_THRESHOLD = "threshold"
OPTION_HALF_LIFE_DAYS = "half_life_days"
OPTION_DEBOUNCE_MINUTES = "debounce_minutes"
OPTION_USERS = "users"

DEFAULTS = {
    OPTION_TOP_SIZE: 3,
    # Two uses in the same slot, and never one. 0.5 let a single click in, which
    # kept a one-off Tuesday air conditioning on the list for a fortnight; 1.5
    # needed three Saturdays where two should do. One click peaks at 1.2 (its
    # slot plus a fifth for the every-day term); two a week apart, checked the
    # week after, give 1.45. tests/test_habits.py pins both edges.
    OPTION_THRESHOLD: 1.25,
    OPTION_HALF_LIFE_DAYS: 14,
    # Several taps a few minutes apart are one intention -- nudging the air
    # conditioning 22, 23, 21 is "set the air conditioning", once.
    OPTION_DEBOUNCE_MINUTES: 5,
    # Empty means every human user.
    OPTION_USERS: [],
}

SERVICE_RESET = "reset"
