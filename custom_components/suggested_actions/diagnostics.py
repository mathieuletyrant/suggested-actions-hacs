"""Everything needed to answer "why is this suggested, or not"."""

from __future__ import annotations

from typing import Any

from homeassistant.core import HomeAssistant

from . import SuggestedActionsConfigEntry
from .const import CONF_ENTITIES


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: SuggestedActionsConfigEntry
) -> dict[str, Any]:
    """Options, the weekday x hour grids, and the last calls kept and turned
    away with their reason.
    """
    found = entry.runtime_data
    return {
        "options": found.options,
        "actions": {
            action_id: {"name": action.title, "entities": action.data[CONF_ENTITIES]}
            for action_id, action in found.actions.items()
        },
        "top": found.top,
        "ranking": found.ranking,
        "usage": found.usage,
        "last_counted": found.last_counted,
        "rejected": list(found.rejected),
    }
