---
name: test-ha
description: Run a throwaway Home Assistant with this integration on a small fake house, make clicks as the owner, and read back what was counted. Use to see a change working in Home Assistant rather than only in tests, "le HA de test", or before and after comparing a branch with main.
---

# test-ha

```bash
R() { python3 scripts/test_ha/run.py "$@"; }   # zsh does not split "$R"
R setup        # once : .venv-ha, the HA requirements_test.txt pins
R start        # fresh instance, owner onboarded, entry and three actions
```

The house: `script.prise_terrasse_minuteur` switches on
`input_boolean.terrasse_l1`, and the actions are `prise_terrasse` (the
script), `l1_exterieur` (the boolean) and `roborock`. That is the terrace
case: one click on the script must count once, for the script.

Then:

1. **Click**: `R call script.prise_terrasse_minuteur`, or
   `R call input_boolean.turn_on '{"entity_id": "input_boolean.roborock"}'`.
   A call made here carries the owner's user, as a dashboard click does.
2. **Read**: `R ranking` for the sensor, `R diagnostics` for the grids (only
   the non-zero slots, as `weekday/hour`) and the rejected calls with their
   reason. `.test-ha/hass.log` has the debug line for every tracked call.
3. **Change the code**, then `R restart`. It recopies the integration.
4. `R stop` when done.

What it cannot show: a click with no user. Every call made from here is the
owner's; an automation is the way to make one, added to `CONFIGURATION` in
`run.py`.
