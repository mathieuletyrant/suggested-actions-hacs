"""Config flow: one entry with a name, five options, and an action per subentry."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    ConfigSubentry,
    ConfigSubentryFlow,
    OptionsFlow,
    SubentryFlowResult,
)
from homeassistant.const import CONF_NAME
from homeassistant.core import callback
from homeassistant.helpers import selector
from homeassistant.util import slugify

from .const import (
    CONF_ACTION_ID,
    CONF_ENTITIES,
    CONF_ICON,
    DEFAULTS,
    DOMAIN,
    OPTION_DEBOUNCE_MINUTES,
    OPTION_HALF_LIFE_DAYS,
    OPTION_THRESHOLD,
    OPTION_TOP_SIZE,
    OPTION_USERS,
    SUBENTRY_ACTION,
)


class SuggestedActionsConfigFlow(ConfigFlow, domain=DOMAIN):
    """One entry per installation (`single_config_entry` in the manifest)."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for a name: it becomes the sensor's, `sensor.<name>_ranking`."""
        if user_input is not None:
            return self.async_create_entry(title=user_input[CONF_NAME], data={})

        french = self.hass.config.language == "fr"
        default = "Actions suggérées" if french else "Suggested actions"
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({vol.Required(CONF_NAME, default=default): str}),
        )

    @staticmethod
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        """The Configure button on the integration card."""
        return SuggestedActionsOptionsFlow()

    @classmethod
    @callback
    def async_get_supported_subentry_types(
        cls, config_entry: ConfigEntry
    ) -> dict[str, type[ConfigSubentryFlow]]:
        """The Add action button on the integration card."""
        return {SUBENTRY_ACTION: ActionSubentryFlow}


def _number(low: float, high: float, step: float) -> selector.NumberSelector:
    return selector.NumberSelector(
        selector.NumberSelectorConfig(
            min=low, max=high, step=step, mode=selector.NumberSelectorMode.BOX
        )
    )


class SuggestedActionsOptionsFlow(OptionsFlow):
    """The five settings worth exposing. The two scoring weights are not among
    them, on purpose -- see habits.py.
    """

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Show the settings, or store what came back."""
        if user_input is not None:
            return self.async_create_entry(data=user_input)

        people = [
            selector.SelectOptionDict(value=user.id, label=user.name or user.id)
            for user in await self.hass.auth.async_get_users()
            if not user.system_generated and user.is_active
        ]
        schema = vol.Schema(
            {
                vol.Required(OPTION_TOP_SIZE): _number(1, 10, 1),
                vol.Required(OPTION_THRESHOLD): _number(0.1, 10, 0.1),
                vol.Required(OPTION_HALF_LIFE_DAYS): _number(1, 90, 1),
                vol.Required(OPTION_DEBOUNCE_MINUTES): _number(0, 60, 1),
                vol.Optional(OPTION_USERS): selector.SelectSelector(
                    selector.SelectSelectorConfig(options=people, multiple=True)
                ),
            }
        )
        return self.async_show_form(
            step_id="init",
            data_schema=self.add_suggested_values_to_schema(
                schema, {**DEFAULTS, **self.config_entry.options}
            ),
        )


def unique_action_id(name: str, taken: set[str]) -> str:
    """`Prise terrasse` -> `prise_terrasse`, then `prise_terrasse_2`."""
    base = slugify(name) or "action"
    candidate, number = base, 2
    while candidate in taken:
        candidate, number = f"{base}_{number}", number + 1
    return candidate


class ActionSubentryFlow(ConfigSubentryFlow):
    """One action: a name, the entities whose calls count for it, an icon."""

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """Add an action."""
        return await self._async_edit("user", user_input)

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """Change one. Without this step the row gets no pencil."""
        return await self._async_edit(
            "reconfigure", user_input, self._get_reconfigure_subentry()
        )

    async def _async_edit(
        self,
        step_id: str,
        user_input: dict[str, Any] | None,
        current: ConfigSubentry | None = None,
    ) -> SubentryFlowResult:
        if user_input is not None:
            data = {CONF_ENTITIES: user_input[CONF_ENTITIES]}
            if icon := user_input.get(CONF_ICON):
                data[CONF_ICON] = icon

            if current is None:
                taken = {
                    subentry.data[CONF_ACTION_ID]
                    for subentry in self._get_entry().subentries.values()
                }
                data[CONF_ACTION_ID] = unique_action_id(user_input[CONF_NAME], taken)
                return self.async_create_entry(title=user_input[CONF_NAME], data=data)

            # The id never follows a rename: dashboard templates spell it.
            data[CONF_ACTION_ID] = current.data[CONF_ACTION_ID]
            return self.async_update_and_abort(
                self._get_entry(), current, title=user_input[CONF_NAME], data=data
            )

        schema = vol.Schema(
            {
                vol.Required(CONF_NAME): selector.TextSelector(),
                vol.Required(CONF_ENTITIES): selector.EntitySelector(
                    selector.EntitySelectorConfig(multiple=True)
                ),
                vol.Optional(CONF_ICON): selector.IconSelector(),
            }
        )
        suggested = {CONF_NAME: current.title, **current.data} if current else {}
        return self.async_show_form(
            step_id=step_id,
            data_schema=self.add_suggested_values_to_schema(schema, suggested),
        )
