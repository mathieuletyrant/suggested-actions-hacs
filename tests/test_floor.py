"""What the declared minimum Home Assistant has to provide.

`hacs.json` names the oldest release this claims to work on, and
`requirements_test_min.txt` makes CI run this file against it. Every module is
imported, and the APIs the integration rests on are named, so raising the
floor -- or finding out it must be raised -- says which call did it.
"""

import importlib
import inspect
import json

import pytest

PACKAGE = "custom_components.suggested_actions"
MODULES = ("config_flow", "const", "diagnostics", "habits", "sensor")
TRANSLATIONS = (
    "custom_components/suggested_actions/strings.json",
    "custom_components/suggested_actions/translations/en.json",
    "custom_components/suggested_actions/translations/fr.json",
)


@pytest.mark.parametrize("name", MODULES)
def test_every_module_imports(name):
    assert importlib.import_module(f"{PACKAGE}.{name}")


def test_habits_never_imports_home_assistant():
    """What keeps the arithmetic testable without an instance."""
    source = inspect.getsource(importlib.import_module(f"{PACKAGE}.habits"))
    assert "homeassistant" not in source.split('"""', 2)[2]


def test_an_action_can_be_a_subentry_and_be_edited():
    from homeassistant.config_entries import ConfigFlow, ConfigSubentryFlow

    assert hasattr(ConfigFlow, "async_get_supported_subentry_types")
    for helper in ("_get_entry", "_get_reconfigure_subentry", "async_update_and_abort"):
        assert hasattr(ConfigSubentryFlow, helper)


def test_a_service_call_event_carries_its_context():
    """The context's user is what tells a click from an automation, and its id
    what ties a script's inner calls to the click that started it.
    """
    from homeassistant.const import EVENT_CALL_SERVICE
    from homeassistant.core import Context

    assert EVENT_CALL_SERVICE == "call_service"
    context = Context(user_id="someone")
    assert context.id
    assert context.user_id == "someone"


def test_unrecorded_attributes_exist():
    from homeassistant.helpers.entity import Entity

    assert hasattr(Entity, "_unrecorded_attributes")


def test_an_entry_can_carry_runtime_data():
    from homeassistant.config_entries import ConfigEntry

    assert "runtime_data" in ConfigEntry.__annotations__


@pytest.mark.parametrize("path", TRANSLATIONS)
def test_every_translation_names_every_field(path):
    from custom_components.suggested_actions.const import DEFAULTS, SUBENTRY_ACTION

    with open(path, encoding="utf-8") as handle:
        strings = json.load(handle)

    assert set(strings["options"]["step"]["init"]["data"]) == set(DEFAULTS)
    steps = strings["config_subentries"][SUBENTRY_ACTION]["step"]
    assert steps["user"]["data"] == steps["reconfigure"]["data"]
    assert strings["entity"]["sensor"]["ranking"]["name"]
    assert strings["services"]["reset"]["fields"]["action"]["name"]


def test_strings_and_english_are_the_same_file():
    with (
        open(TRANSLATIONS[0], encoding="utf-8") as strings,
        open(TRANSLATIONS[1], encoding="utf-8") as english,
    ):
        assert json.load(strings) == json.load(english)


def test_the_declared_floor_is_the_one_the_tests_run_against():
    with open("hacs.json", encoding="utf-8") as handle:
        declared = json.load(handle)["homeassistant"]
    with open("requirements_test_min.txt", encoding="utf-8") as handle:
        pinned = [
            line.split("==")[1].strip()
            for line in handle
            if line.startswith("homeassistant==")
        ]
    assert pinned == [declared]
