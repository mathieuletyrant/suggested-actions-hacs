"""A throwaway Home Assistant running this integration on a small fake house.

Starts Home Assistant with the integration copied from the working tree,
onboards an owner, adds the entry and three actions -- one of them a script
that switches on another tracked entity, the terrace case -- so the result is
an instance where clicks can be made and their counting read back.
`.claude/skills/test-ha` is the walk-through.

    python scripts/test_ha/run.py setup            # once : the HA venv
    python scripts/test_ha/run.py start            # fresh instance
    python scripts/test_ha/run.py restart          # recopy the code, restart
    python scripts/test_ha/run.py stop
    python scripts/test_ha/run.py call DOMAIN.SERVICE [JSON]   # as the owner
    python scripts/test_ha/run.py ranking          # the sensor and its attributes
    python scripts/test_ha/run.py diagnostics      # grids, kept and rejected calls
    python scripts/test_ha/run.py token            # a fresh access token

A call made here carries the owner's user, exactly as a dashboard click does.
Home Assistant runs from `.venv-ha` (or HA_PYTHON), the version
`requirements_test.txt` pins. State lives in TEST_HA_DIR (default `.test-ha`),
which `start` wipes.
"""

import json
import os
import pathlib
import re
import shutil
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent.parent
WORK = pathlib.Path(os.environ.get("TEST_HA_DIR", ROOT / ".test-ha")).resolve()
CONFIG = WORK / "config"
VENV = ROOT / ".venv-ha"
PYTHON = os.environ.get("HA_PYTHON", str(VENV / "bin" / "python"))
DOMAIN = "suggested_actions"
SENSOR = "sensor.actions_suggerees_classement"

HA_URL = "http://127.0.0.1:8123"
CLIENT_ID = HA_URL + "/"

OWNER = {"name": "Test", "username": "test", "password": "test-password"}

# input_boolean stands in for the real switches and the robot: what matters is
# that they are entities a service call can name.
CONFIGURATION = """\
homeassistant:
  time_zone: Europe/Paris
  country: FR
  language: fr
  unit_system: metric

default_config:

logger:
  default: warning
  logs:
    custom_components.suggested_actions: debug

input_boolean:
  terrasse_l1:
    name: Terrasse L1
  roborock:
    name: Roborock

script:
  prise_terrasse_minuteur:
    alias: Prise terrasse minuteur
    sequence:
      - action: input_boolean.turn_on
        target:
          entity_id: input_boolean.terrasse_l1
"""

ACTIONS = [
    {"name": "Prise terrasse", "entities": ["script.prise_terrasse_minuteur"]},
    {"name": "L1 extérieur", "entities": ["input_boolean.terrasse_l1"]},
    {
        "name": "Roborock",
        "entities": ["input_boolean.roborock"],
        "icon": "mdi:robot-vacuum",
    },
]


def request(method, path, body=None, form=None, token=None, base=HA_URL):
    """One HTTP call, JSON in and out, exiting on anything but 2xx."""
    data, headers = None, {}
    if form is not None:
        data = urllib.parse.urlencode(form).encode()
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    elif body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = f"Bearer {token}"

    req = urllib.request.Request(base + path, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=120) as response:
            raw = response.read()
    except urllib.error.HTTPError as err:
        raise SystemExit(
            f"{method} {path} answered {err.code}: {err.read().decode()[:500]}"
        ) from err
    try:
        return json.loads(raw) if raw else None
    except ValueError:
        return raw.decode()


def wait_for(url, seconds):
    """Until the URL answers with anything but a 404, or give up."""
    deadline = time.time() + seconds
    while time.time() < deadline:
        try:
            urllib.request.urlopen(url, timeout=10)
            return
        except urllib.error.HTTPError as err:
            if err.code != 404:
                return
        except OSError:
            pass
        time.sleep(2)
    raise SystemExit(f"{url} did not come up within {seconds}s ; see {WORK}/*.log")


def spawn(name, argv):
    """Start a process detached from this one, its output in WORK/<name>.log."""
    log = open(WORK / f"{name}.log", "ab")  # noqa: SIM115 -- the child keeps it
    # Not from the repository : `python -m` puts the working directory on the
    # path, and its `custom_components` would shadow the patched copy.
    # S603: argv is built here from this interpreter and this repository.
    process = subprocess.Popen(  # noqa: S603
        argv,
        stdout=log,
        stderr=subprocess.STDOUT,
        start_new_session=True,
        cwd=WORK,
    )
    (WORK / f"{name}.pid").write_text(str(process.pid))


def kill(name):
    pidfile = WORK / f"{name}.pid"
    if not pidfile.exists():
        return
    pid = int(pidfile.read_text())
    try:
        os.killpg(pid, signal.SIGTERM)
        for _ in range(30):
            os.kill(pid, 0)
            time.sleep(1)
        os.killpg(pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    pidfile.unlink()


def copy_integration():
    """The working tree's integration, as it is."""
    target = CONFIG / "custom_components" / DOMAIN
    shutil.rmtree(target, ignore_errors=True)
    shutil.copytree(
        ROOT / "custom_components" / DOMAIN,
        target,
        ignore=shutil.ignore_patterns("__pycache__"),
    )


def add_entry():
    """The config flow, then one subentry flow per action, as the UI runs them."""
    token = access_token()
    flow = request(
        "POST", "/api/config/config_entries/flow", {"handler": DOMAIN}, token=token
    )
    step = request(
        "POST",
        f"/api/config/config_entries/flow/{flow['flow_id']}",
        {"name": "Actions suggérées"},
        token=token,
    )
    if step.get("type") != "create_entry":
        raise SystemExit(f"The config flow stopped at {step}")
    entry_id = step["result"]["entry_id"]
    (WORK / "entry_id").write_text(entry_id)

    for action in ACTIONS:
        flow = request(
            "POST",
            "/api/config/config_entries/subentries/flow",
            {"handler": [entry_id, "action"]},
            token=token,
        )
        step = request(
            "POST",
            f"/api/config/config_entries/subentries/flow/{flow['flow_id']}",
            action,
            token=token,
        )
        if step.get("type") != "create_entry":
            raise SystemExit(f"The subentry flow stopped at {step}")


def start_ha():
    if not pathlib.Path(PYTHON).exists():
        raise SystemExit(f"No Home Assistant interpreter at {PYTHON} ; run setup")
    spawn("hass", [PYTHON, "-m", "homeassistant", "-c", str(CONFIG)])
    # The API answers before startup is over ; onboarding only once the
    # default integrations are set up, which on a first start includes
    # installing their requirements.
    wait_for(HA_URL + "/api/", 900)
    if not (WORK / "tokens.json").exists():
        wait_for(HA_URL + "/api/onboarding", 900)
        return
    # Once onboarded, /api/onboarding is gone for good -- a 404 forever, which
    # wait_for reads as "not up yet". The sensor existing is the signal instead.
    deadline = time.time() + 300
    while time.time() < deadline:
        found = request("GET", "/api/states", token=access_token())
        if any(state["entity_id"] == SENSOR for state in found):
            return
        time.sleep(2)
    raise SystemExit(f"{SENSOR} did not appear ; see {WORK}/hass.log")


def onboard():
    """Create the owner and finish onboarding ; keep a refresh token."""
    code = request(
        "POST",
        "/api/onboarding/users",
        {**OWNER, "client_id": CLIENT_ID, "language": "fr"},
    )["auth_code"]
    tokens = request(
        "POST",
        "/auth/token",
        form={"grant_type": "authorization_code", "code": code, "client_id": CLIENT_ID},
    )
    (WORK / "tokens.json").write_text(json.dumps(tokens))

    access = tokens["access_token"]
    request("POST", "/api/onboarding/core_config", {}, token=access)
    request("POST", "/api/onboarding/analytics", {}, token=access)
    request(
        "POST",
        "/api/onboarding/integration",
        {"client_id": CLIENT_ID, "redirect_uri": CLIENT_ID},
        token=access,
    )


def access_token():
    tokens = json.loads((WORK / "tokens.json").read_text())
    return request(
        "POST",
        "/auth/token",
        form={
            "grant_type": "refresh_token",
            "refresh_token": tokens["refresh_token"],
            "client_id": CLIENT_ID,
        },
    )["access_token"]


def setup():
    """The venv Home Assistant runs from, at the version the tests pin."""
    pin = re.search(
        r"^homeassistant==(\S+)", (ROOT / "requirements_test.txt").read_text(), re.M
    )
    if pin is None:
        raise SystemExit("requirements_test.txt pins no homeassistant")
    uv = shutil.which("uv") or "uv"
    subprocess.run(  # noqa: S603 -- fixed arguments
        [uv, "venv", "-q", "--python", "3.14.2", str(VENV)], check=True
    )
    subprocess.run(  # noqa: S603 -- fixed arguments
        [
            uv,
            "pip",
            "install",
            "-q",
            "--python",
            str(VENV / "bin" / "python"),
            f"homeassistant=={pin.group(1)}",
        ],
        check=True,
    )
    print(f"Home Assistant {pin.group(1)} in {VENV}")


def start():
    kill("hass")
    shutil.rmtree(WORK, ignore_errors=True)
    CONFIG.mkdir(parents=True)
    (CONFIG / "configuration.yaml").write_text(CONFIGURATION)
    copy_integration()
    start_ha()
    onboard()
    add_entry()
    print(f"Home Assistant is up on {HA_URL}, owner {OWNER['username']}")


def restart():
    kill("hass")
    copy_integration()
    start_ha()
    print(f"Restarted on {HA_URL}")


def call(service, data="{}"):
    domain, name = service.split(".", 1)
    result = request(
        "POST", f"/api/services/{domain}/{name}", json.loads(data), token=access_token()
    )
    print(json.dumps(result, indent=1, ensure_ascii=False))


def ranking():
    state = request("GET", f"/api/states/{SENSOR}", token=access_token())
    print(json.dumps(state, indent=1, ensure_ascii=False))


def diagnostics():
    entry_id = (WORK / "entry_id").read_text()
    found = request(
        "GET", f"/api/diagnostics/config_entry/{entry_id}", token=access_token()
    )
    data = found["data"]
    for usage in data["usage"].values():
        # 168 zeros say nothing; the slots that hold something do.
        usage["grid"] = {
            f"{day}/{hour}h": round(count, 3)
            for day, row in enumerate(usage["grid"])
            for hour, count in enumerate(row)
            if count
        }
    print(json.dumps(data, indent=1, ensure_ascii=False))


def main():
    args = sys.argv[1:]
    commands = {
        "setup": (setup, 0, 0),
        "start": (start, 0, 0),
        "restart": (restart, 0, 0),
        "stop": (lambda: kill("hass"), 0, 0),
        "call": (call, 1, 2),
        "ranking": (ranking, 0, 0),
        "diagnostics": (diagnostics, 0, 0),
        "token": (lambda: print(access_token()), 0, 0),
    }
    if not args or args[0] not in commands:
        raise SystemExit(__doc__)
    function, least, most = commands[args[0]]
    rest = args[1:]
    if not least <= len(rest) <= most:
        raise SystemExit(__doc__)
    function(*rest)


if __name__ == "__main__":
    main()
