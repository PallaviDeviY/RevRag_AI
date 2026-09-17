# RevRag AI — Android Controller & Observation (Member 1)

This repository module is the **hands and eyes** of RevRag AI: it installs and drives an Android app, then publishes **Observation JSON** plus screenshot and UI-hierarchy artifacts for the rest of the team.

It does **not** implement the AI agent, knowledge/RAG engine, dashboard, or report generator.

```text
Member 2  --Action JSON-->  Member 1 (this module)  --Observation JSON-->  Members 2, 3, 4
                                      |
                                      +-- data/screenshots/*.png
                                      +-- data/ui_trees/*.xml
                                      +-- data/observations/*.json
```

Other members should integrate through that JSON contract only — not through Python class names, ADB commands, or Windows paths.

## Project

Given an APK path and later Action JSON, this module:

1. Validates and installs the APK on a connected emulator/device
2. Launches (or resets) the application
3. Executes tap / type / scroll / back / home / launch / restart
4. Waits for the UI to settle
5. Captures a screenshot and a UIAutomator XML dump
6. Parses UI elements (including stable `element_id` values)
7. Writes Observation JSON under `data/observations/`

Failures return structured `{ "success": false, "error": { "code", "message" } }` instead of crashing the exploration loop.

## Prerequisites

* Python **3.10+**
* Android SDK Platform-Tools (`adb` on `PATH`, or set `ADB_PATH`)
* Android emulator **or** a USB-debuggable device
* (Optional) `aapt` / `aapt2` to read the package name from an APK before install
* (Optional) OpenCV — listed in `requirements.txt` for screenshot similarity; the controller works without it

## Installation

```bash
cd RevRag_AI
python -m venv .venv

# Windows
.venv\Scripts\activate

# macOS / Linux
source .venv/bin/activate

pip install -r requirements.txt
copy .env.example .env   # Windows
# cp .env.example .env   # macOS / Linux
```

Do not commit `.env`. Configure at least:

```env
ADB_PATH=adb
ANDROID_SERIAL=
DEFAULT_TIMEOUT=10
UI_SETTLE_TIMEOUT=5
SCREENSHOT_DIR=data/screenshots
UI_TREE_DIR=data/ui_trees
OBSERVATION_DIR=data/observations
ANDROID_MOCK=0
```

Leave `ANDROID_SERIAL` empty to auto-select the first emulator, then the first online device. Never hard-code `emulator-5554`.

## Emulator setup

```bash
# List AVDs
emulator -list-avds

# Start one (example name)
emulator -avd Pixel_6_API_34
```

Set `ANDROID_AVD` and `EMULATOR_PATH` if you want this module to launch the AVD for you.

## ADB verification

```bash
adb devices
python scripts/check_android_env.py
python main.py check
```

You should see a device in state `device` (not `offline` or `unauthorized`).

## Running tests

Unit tests are mock/offline and must not require an emulator:

```bash
pytest
```

Real-device/emulator integration tests are opt-in:

```bash
pytest -m android
```

## Running the demo

Mock (no emulator):

```bash
python scripts/run_demo.py --mock
```

Real APK (path supplied by you — nothing is hardcoded):

```bash
python scripts/run_demo.py --apk path/to/app.apk
```

Flow:

```text
APK → install → launch → Observation #1 → Action JSON → Observation #2
```

## CLI

```bash
python main.py check
python main.py install --apk app.apk
python main.py launch --package com.example.app
python main.py screenshot
python main.py observe
python main.py execute --action data/sample/action_tap.json
python main.py reset --package com.example.app
python main.py --mock observe
python main.py --mock execute --action data/sample/action_tap.json
```

`--mock` runs the in-memory backend so Member 2 can integrate without Android SDK.

## JSON contracts

### Action JSON (Member 2 → Member 1)

```json
{
  "action_id": "action_000001",
  "action_type": "tap",
  "element_id": "element_000004",
  "bounds": { "left": 100, "top": 400, "right": 500, "bottom": 480 }
}
```

Supported `action_type` values: `tap`, `type`, `scroll`, `swipe`, `back`, `home`, `launch`, `restart`.

Target resolution: `element_id` first, then valid `bounds`. The module will not tap arbitrary coordinates if neither is usable.

### Observation JSON (Member 1 → Members 2, 3, 4)

```json
{
  "observation_id": "obs_000001",
  "screen_id": "screen_000001",
  "timestamp": "2026-09-17T21:30:00+05:30",
  "package_name": "com.example.app",
  "activity": "com.example.app.MainActivity",
  "screenshot_path": "screenshots/obs_000001.png",
  "ui_tree_path": "ui_trees/obs_000001.xml",
  "elements": []
}
```

Resolve files as:

```text
data/ + screenshot_path  →  data/screenshots/obs_000001.png
data/ + ui_tree_path     →  data/ui_trees/obs_000001.xml
data/observations/obs_000001.json
```

IDs:

| Field | Format | Stability |
| --- | --- | --- |
| `observation_id` | `obs_000001` | Sequential per controller session |
| `screen_id` | `screen_000001` | First time a UI fingerprint is seen; reused for the same UI |
| `element_id` | `element_000001` | DFS order of that dump (deterministic for the same XML) |
| `action_id` | caller-supplied | Never rewritten |

Schemas live in `schemas/` and are provisional until the team publishes a shared pack. Prefer those files over this README if they differ.

### Errors

```json
{
  "success": false,
  "error": {
    "code": "ELEMENT_NOT_FOUND",
    "message": "Target element could not be resolved",
    "action_id": "action_000004"
  }
}
```

Password typing is logged as `Typing text into password field [REDACTED]`.

## Folder structure

```text
android/           Controller implementation
schemas/           Action / Observation / Element JSON schemas
data/screenshots/  PNG artifacts (relative paths in JSON)
data/ui_trees/     UIAutomator XML artifacts
data/observations/ Observation JSON for the dashboard timeline
data/sample/       Example Action + Observation payloads
data/apk/          Local APK drop folder (APKs are gitignored)
tests/             Offline unit tests + optional -m android
scripts/           Env check + demo
docs/              Integration notes for Members 2–4
```

## Troubleshooting

| Symptom | What to do |
| --- | --- |
| ADB not found | Install platform-tools; set `ADB_PATH` to the `adb` executable |
| emulator offline | `adb kill-server && adb start-server`; wait until state is `device` |
| APK installation failed | Confirm the APK is valid, device has space, and API level matches |
| UIAutomator dump failed | App may be in a secure/blocked activity; retry after settle; check `adb shell uiautomator dump` |
| screenshot failed | `adb exec-out screencap -p` must return bytes; avoid piping through a text shell on Windows |
| element not found | Use `element_id` from the **latest** Observation JSON; IDs are per dump |

## License / secrets

Do not commit API keys, `.env`, passwords, or APKs. `.gitignore` already excludes `.env` and `*.apk`.
