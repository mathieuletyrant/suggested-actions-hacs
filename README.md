# ⭐ Suggested Actions

A Home Assistant integration that learns which quick actions you click **at
this time of day and on this day of the week**, and puts them first on your
dashboard.

No AI, no schedule to write: it counts your clicks and ranks them. It
**suggests, never runs** — nothing is triggered on your behalf.

## ✨ What you get

- 📊 **One sensor**, `sensor.<name>_ranking` (`sensor.actions_suggerees_classement`
  on a French install). Its state is the top suggestion; its `top` attribute
  lists every suggestion, in order.
- 🧠 **Learning from real clicks only** — a service call made by a person, from
  a dashboard or the app. Automations, physical buttons and voice satellites
  have no user, so they never count.
- 📅 **Weekday × hour habits** — a Saturday-morning vacuum is suggested on
  Saturday mornings, not every morning.
- 🍂 **Habits fade** — with a 14-day half-life, something you stopped doing drops
  off on its own.
- 🔍 **Easy to debug** — the `ranking` attribute shows every action's score,
  the debug log says why each click was or was not counted, and the
  diagnostics download holds the full grids.

## 📦 Installation

1. HACS → ⋮ → **Custom repositories** → add
   `https://github.com/mathieuletyrant/suggested-actions-hacs`, category
   **Integration**.
2. Install **Suggested Actions**, restart Home Assistant.
3. **Settings → Devices & services → Add integration → Suggested Actions**.
4. On the integration card, **Add an action** for each quick action: a name and
   the entities whose clicks count for it. An action can group several entities
   — an air conditioning script and the climate entity itself.

Requires Home Assistant **2025.4** or newer.

## 🃏 Using it in a dashboard

The action id is the slug of its name (`Prise terrasse` → `prise_terrasse`),
fixed when the action is created. Read it from the `top` attribute.

**A star on suggested actions** (Mushroom cards):

```yaml
badge_icon: >-
  {{ 'mdi:star' if 'roborock' in (state_attr('sensor.actions_suggerees_classement', 'top') or []) else '' }}
badge_color: amber
```

**Hide what is not suggested** (Home Assistant 2026.10+, Visibility tab):

```yaml
visibility:
  - condition: template
    value_template: >-
      {{ 'roborock' in (state_attr('sensor.actions_suggerees_classement', 'top') or []) }}
```

Keep the actions you may need at any moment — the alarm — always visible.

## ⚙️ Options

| Option | Default | What it does |
| --- | --- | --- |
| Number of suggestions | 3 | How many actions `top` lists at most |
| Suggestion threshold | 1.25 | About two uses at the same moment; one click never makes it |
| Half-life | 14 days | After this long, a use counts half as much |
| Anti-duplicate window | 5 min | Several clicks on one action within it count once |
| Users to learn from | everyone | Restrict learning to some accounts |

## 🛠️ Actions

`suggested_actions.reset` forgets one action (`action: roborock`) or all of
them.
