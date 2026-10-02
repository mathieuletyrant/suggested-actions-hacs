"""The one entity: which actions to suggest right now."""

from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import Habits, SuggestedActionsConfigEntry
from .const import CONF_ENTITIES, DOMAIN


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SuggestedActionsConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """One sensor per entry."""
    async_add_entities([RankingSensor(entry, entry.runtime_data)])


class RankingSensor(SensorEntity):
    """State: the first suggestion. `top`: every suggestion, in order."""

    _attr_has_entity_name = True
    _attr_translation_key = "ranking"
    _attr_should_poll = False
    # `top` is what dashboards read and what is worth a history. The full
    # ranking moves every quarter of an hour and would only fill the database.
    _unrecorded_attributes = frozenset({"ranking", "last_update"})

    def __init__(self, entry: SuggestedActionsConfigEntry, found: Habits) -> None:
        """Hang off a service device named after the entry, which is what
        makes the id `sensor.<entry name>_<ranking>`.
        """
        self._habits = found
        self._attr_unique_id = f"{entry.entry_id}_ranking"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.title,
            entry_type=DeviceEntryType.SERVICE,
        )

    async def async_added_to_hass(self) -> None:
        """Write the state after every re-rank."""
        self.async_on_remove(self._habits.add_listener(self.async_write_ha_state))

    @property
    def native_value(self) -> str | None:
        """The first suggestion, or nothing until some habit is learnt."""
        return self._habits.top[0] if self._habits.top else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """The suggestions, and the whole ranking for whoever is debugging."""
        actions = self._habits.actions
        return {
            "top": list(self._habits.top),
            "ranking": [
                {
                    "id": action_id,
                    "name": actions[action_id].title,
                    "score": round(score, 2),
                    "entities": list(actions[action_id].data[CONF_ENTITIES]),
                }
                for action_id, score in self._habits.ranking
            ],
            "last_update": self._habits.updated_at.isoformat()
            if self._habits.updated_at
            else None,
        }
