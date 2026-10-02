"""Suggested actions: learn which quick actions get clicked when, and rank them.

Listens for service calls a person made, counts them per weekday x hour, and
exposes the ranking as one sensor. It suggests; it never runs anything.
"""

from __future__ import annotations

from collections import deque
from collections.abc import Callable
from datetime import datetime, timedelta
import logging

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.const import EVENT_CALL_SERVICE, Platform
from homeassistant.core import Event, HomeAssistant, ServiceCall, callback
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.storage import Store
from homeassistant.helpers.typing import ConfigType
from homeassistant.util import dt as dt_util

from . import habits
from .const import (
    CONF_ACTION_ID,
    CONF_ENTITIES,
    DEFAULTS,
    DOMAIN,
    OPTION_DEBOUNCE_MINUTES,
    OPTION_HALF_LIFE_DAYS,
    OPTION_THRESHOLD,
    OPTION_TOP_SIZE,
    OPTION_USERS,
    SERVICE_RESET,
    SUBENTRY_ACTION,
)

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.SENSOR]
CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

STORAGE_VERSION = 1
SAVE_DELAY = 30
# The score moves with the clock even when nobody clicks: the hour turns, the
# old counts fade. A quarter of an hour is fine-grained enough for a slot that
# is an hour wide.
REFRESH = timedelta(minutes=15)

type SuggestedActionsConfigEntry = ConfigEntry[Habits]


class Habits:
    """The counts for one entry, and the ranking they currently give."""

    def __init__(
        self, hass: HomeAssistant, entry: ConfigEntry, store: Store, stored: dict
    ) -> None:
        """Keep the counts of the actions that still exist, and nothing else."""
        self.hass = hass
        self.store = store
        self.options = {**DEFAULTS, **entry.options}
        self.actions = {
            subentry.data[CONF_ACTION_ID]: subentry
            for subentry in entry.subentries.values()
            if subentry.subentry_type == SUBENTRY_ACTION
        }
        self.by_entity: dict[str, set[str]] = {}
        for action_id, subentry in self.actions.items():
            for entity_id in subentry.data[CONF_ENTITIES]:
                self.by_entity.setdefault(entity_id, set()).add(action_id)

        # A deleted action takes its counts with it; a new one starts at zero.
        self.usage = {
            action_id: stored.get(action_id) or habits.empty_usage()
            for action_id in self.actions
        }
        if set(stored) != set(self.usage):
            self.save()

        self.seen: deque[str] = deque(maxlen=64)
        self.rejected: deque[dict] = deque(maxlen=20)
        self.last_counted: dict | None = None
        self.ranking: list[tuple[str, float]] = []
        self.top: list[str] = []
        self.updated_at: datetime | None = None
        self._listeners: list[Callable[[], None]] = []

    @property
    def half_life(self) -> float:
        """In seconds, as the timestamps are."""
        return self.options[OPTION_HALF_LIFE_DAYS] * 86400

    def add_listener(self, listener: Callable[[], None]) -> Callable[[], None]:
        """Call `listener` after every refresh; returns the unsubscribe."""
        self._listeners.append(listener)
        return lambda: self._listeners.remove(listener)

    @callback
    def refresh(self, *_args) -> None:
        """Re-rank for the current weekday and hour."""
        now = dt_util.now()
        stamp = now.timestamp()
        self.ranking = habits.rank(
            (
                action_id,
                habits.score(usage, stamp, now.weekday(), now.hour, self.half_life),
                usage["last_used"],
            )
            for action_id, usage in self.usage.items()
        )
        self.top = habits.top(
            self.ranking,
            int(self.options[OPTION_TOP_SIZE]),
            self.options[OPTION_THRESHOLD],
        )
        self.updated_at = now
        for listener in self._listeners:
            listener()

    def save(self) -> None:
        """Write within the next half-minute, batching a burst of clicks."""
        self.store.async_delay_save(lambda: {"usage": self.usage}, SAVE_DELAY)

    @callback
    def on_call(self, event: Event) -> None:
        """Every service call on the bus passes here, so this stays cheap.

        Calls on no tracked entity stop at the first line, unlogged: logging
        them would be every light switched on anywhere in the house.
        """
        data = event.data
        entities = habits.entities_of_call(
            data.get("domain", ""),
            data.get("service", ""),
            data.get("service_data") or {},
        )
        actions = sorted({a for e in entities for a in self.by_entity.get(e, ())})
        if actions:
            self.hass.async_create_task(self._async_count(event, actions))

    async def _async_count(self, event: Event, actions: list[str]) -> None:
        call = f"{event.data.get('domain')}.{event.data.get('service')}"
        now = dt_util.now()
        reason = await self._async_user_reason(event.context.user_id)
        counted: list[str] = []
        if reason is None:
            counted, reason = habits.admit(
                actions,
                event.context.id,
                self.seen,
                {action: self.usage[action]["last_used"] for action in actions},
                now.timestamp(),
                self.options[OPTION_DEBOUNCE_MINUTES] * 60,
            )

        if reason:
            _LOGGER.debug("%s on %s not counted: %s", call, actions, reason)
            self.rejected.append(
                {
                    "at": now.isoformat(),
                    "call": call,
                    "actions": actions,
                    "reason": reason,
                }
            )
            return

        for action_id in counted:
            habits.record(
                self.usage[action_id],
                now.timestamp(),
                now.weekday(),
                now.hour,
                self.half_life,
            )
        _LOGGER.debug("%s counted for %s", call, counted)
        self.last_counted = {"at": now.isoformat(), "call": call, "actions": counted}
        self.refresh()
        self.save()

    async def _async_user_reason(self, user_id: str | None) -> str | None:
        """Why this caller is not a person this learns from, or None if it is.

        An automation, a physical button or a voice satellite calls with no
        user; the Supervisor and the cloud call as system users.
        """
        if not user_id:
            return habits.NO_USER
        user = await self.hass.auth.async_get_user(user_id)
        if user is None or user.system_generated:
            return habits.NO_USER
        followed = self.options[OPTION_USERS]
        if followed and user_id not in followed:
            return habits.USER_NOT_FOLLOWED
        return None

    def reset(self, action_id: str | None) -> None:
        """Forget one action, or all of them."""
        for target in [action_id] if action_id else list(self.usage):
            self.usage[target] = habits.empty_usage()
        self.refresh()
        self.save()


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Register the reset action once, whatever the entries do."""

    async def _reset(call: ServiceCall) -> None:
        action_id = call.data.get("action")
        for entry in hass.config_entries.async_entries(DOMAIN):
            if entry.state is not ConfigEntryState.LOADED:
                continue
            if action_id and action_id not in entry.runtime_data.usage:
                raise ServiceValidationError(f"No action called {action_id}")
            entry.runtime_data.reset(action_id)

    hass.services.async_register(
        DOMAIN,
        SERVICE_RESET,
        _reset,
        schema=vol.Schema({vol.Optional("action"): cv.string}),
    )
    return True


def _store(hass: HomeAssistant, entry: ConfigEntry) -> Store:
    return Store(hass, STORAGE_VERSION, f"{DOMAIN}.{entry.entry_id}")


async def async_setup_entry(
    hass: HomeAssistant, entry: SuggestedActionsConfigEntry
) -> bool:
    """Load the counts, start listening, and rank once straight away."""
    store = _store(hass, entry)
    stored = await store.async_load() or {}
    entry.runtime_data = found = Habits(hass, entry, store, stored.get("usage", {}))

    entry.async_on_unload(hass.bus.async_listen(EVENT_CALL_SERVICE, found.on_call))
    entry.async_on_unload(async_track_time_interval(hass, found.refresh, REFRESH))
    # Options and subentries both land here, and a reload is all either needs.
    entry.async_on_unload(entry.add_update_listener(_async_reload))

    found.refresh()
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def _async_reload(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(
    hass: HomeAssistant, entry: SuggestedActionsConfigEntry
) -> bool:
    """Write now rather than in thirty seconds: a reload reads the file back
    straight away, and would otherwise lose the last clicks.
    """
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        await entry.runtime_data.store.async_save({"usage": entry.runtime_data.usage})
    return unloaded


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """The counts are the integration's only state; they go with it."""
    await _store(hass, entry).async_remove()
