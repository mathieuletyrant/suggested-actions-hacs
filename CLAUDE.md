# Suggested Actions — Home Assistant integration

Counts the service calls a person makes on tracked entities, per weekday ×
hour, and ranks the actions for the current moment in one sensor. It suggests;
it never calls a service itself. The spec, with every decision and why, is
the Claude doc "Spécifications — intégration « Actions suggérées »"
(https://claude.ai/artifact/6nyYfSEAJfKE8HZxDXNpLU).

## Shape

| File | What it holds |
| ---- | ------------- |
| `habits.py` | Counting, forgetting, scoring, ranking, and the click rules (`admit`). **Never imports homeassistant** — `tests/test_floor.py` checks it. A rule that needs `hass` does not belong here. |
| `__init__.py` | `Habits`: the listener on `EVENT_CALL_SERVICE`, the user check, the store, the 15-minute refresh; the `reset` action. |
| `sensor.py` | The one entity. `top` is recorded; `ranking` and `last_update` are not. |
| `config_flow.py` | Entry (a name), options (five), and the action subentry with its reconfigure step. |
| `diagnostics.py` | Options, grids, last counted call, last 20 rejected with their reason. |

## Things not to undo

**One click is one use, by `context.id`.** A script runs its inner service
calls under the caller's context — read in `homeassistant/core.py` and
`components/script`, and seen on the test instance: the terrace script
switching on L1 arrives as a second call with the same id. `admit` remembers
the context *before* the duplicate check, so a duplicate script click still
hides its inner calls. `tests/test_habits.py` pins both.

**Forgetting is by time, applied on read.** `updated` is when the grid was last
written; `score` multiplies by `0.5 ** (elapsed / half_life)`. No timer writes
anything, and an action nobody uses fades even if nothing else is used either.
The prototype forgot by use (×0.98 per click anywhere), which kept a dropped
habit alive in a quiet house.

**The threshold default is 1.25, not 1.5.** One click peaks at 1.2; two a
week apart, read the week after, give 1.45. 1.5 needed three Saturdays.

**Untracked calls are not logged.** `on_call` sees every service call in the
house; it returns before logging anything unless a tracked entity is named.

**Weights are constants.** `NEIGHBOUR_WEIGHT` and `EVERY_DAY_WEIGHT` are not
options on purpose: nobody can say what changing them would do.

**Action ids never change after creation.** Dashboard templates spell them.

## Tests

Python 3.14.2. `uv venv --python 3.14.2`, `uv pip install -r
requirements_test.txt -r requirements_lint.txt`, `.venv/bin/pytest tests/ -q`,
`.venv/bin/ruff check .`. CI runs the same, plus the floor
(`requirements_test_min.txt`, HA 2025.4.0 — the 2025.3.x line pins a yanked
aiohttp and cannot be installed), hassfest and HACS validation.

End to end: `.claude/skills/test-ha` — a real Home Assistant with a fake
house, clicks made as the owner, diagnostics read back.

## Releasing

CalVer. Bump `version` in `custom_components/suggested_actions/manifest.json`
and write `release_notes/<version>.md` (skill `release-notes`) in the same
pull request, merge, then dispatch the **Release** workflow with the same
version. Pull request bodies: skill `pr-description`.
