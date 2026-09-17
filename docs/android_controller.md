# Android Controller — team integration (Member 1)

This module is the **Observation Provider**. Members 2–4 should depend only on:

```text
Action JSON  →  Observation JSON  →  data/screenshots/*  and  data/ui_trees/*
```

Do not import private Python helpers, ADB command strings, or absolute Windows paths.

## How to start the controller

```bash
pip install -r requirements.txt
python main.py check
python main.py --mock observe          # no emulator
python main.py launch --package com.example.app
```

## How to provide an APK

```bash
python main.py install --apk path/to/app.apk
python scripts/run_demo.py --apk path/to/app.apk
```

The path is an argument (or `APK_PATH` in `.env`). No APK filename is hardcoded.

## How Member 2 sends Action JSON

Write a JSON file (or POST/pass a dict in-process) matching `schemas/action.schema.json`.

Input:

```json
{
  "action_id": "action_000001",
  "action_type": "tap",
  "element_id": "element_000004",
  "bounds": {
    "left": 100,
    "top": 400,
    "right": 500,
    "bottom": 480
  }
}
```

```bash
python main.py execute --action data/sample/action_tap.json
```

In Python (still using the public JSON-shaped API):

```python
from android.actions import ActionExecutor

executor = ActionExecutor(mock=True)          # or mock=False with an emulator
executor.launch("com.example.app")            # initial Observation
result = executor.execute({
    "action_id": "action_000001",
    "action_type": "tap",
    "element_id": "element_000004",
    "bounds": {"left": 100, "top": 400, "right": 500, "bottom": 480},
})
print(result.to_dict())
```

Controller execution:

```text
Resolve element → ADB tap → wait for UI settle → screenshot → UI XML → Observation
```

## How to receive Observation JSON

On success, `result.to_dict()` looks like:

```json
{
  "success": true,
  "action": { "action_id": "action_000001", "action_type": "tap" },
  "observation": {
    "observation_id": "obs_000002",
    "screen_id": "screen_000002",
    "timestamp": "2026-09-17T21:30:00+05:30",
    "package_name": "com.example.app",
    "activity": "com.example.app.MainActivity",
    "screenshot_path": "screenshots/obs_000002.png",
    "ui_tree_path": "ui_trees/obs_000002.xml",
    "caused_by_action_id": "action_000001",
    "elements": []
  }
}
```

The same observation is written to `data/observations/obs_000002.json` for Member 4 (timeline) and Member 3 (knowledge extraction).

### Paths

All artifact paths in JSON are relative to `data/`:

| JSON field | Resolves to |
| --- | --- |
| `screenshots/obs_000002.png` | `data/screenshots/obs_000002.png` |
| `ui_trees/obs_000002.xml` | `data/ui_trees/obs_000002.xml` |

## element_id

In each dump, nodes are walked depth-first and numbered `element_000001`, `element_000002`, …  
The AI Agent must read `element_id` values from the **latest** observation. Do not reuse IDs from an older screen.

`screen_id` stays stable when the UI fingerprint (types, resource-ids, text, bounds) matches a screen already seen in this session.

## Errors

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

Exploration should continue to the next planned action. Codes include `APK_NOT_FOUND`, `INVALID_APK`, `ADB_UNAVAILABLE`, `EMULATOR_UNAVAILABLE`, `INSTALLATION_FAILED`, `LAUNCH_FAILED`, `UI_DUMP_FAILED`, `SCREENSHOT_FAILED`, `ELEMENT_NOT_FOUND`, `INVALID_BOUNDS`, `ACTION_TIMEOUT`, `UNSUPPORTED_ACTION`, `TEXT_INPUT_FAILED`, `SCROLL_FAILED`, `SUBPROCESS_ERROR`.

## Mock vs real emulator

| Mode | How | Needs Android SDK |
| --- | --- | --- |
| Mock | `ANDROID_MOCK=1` or `python main.py --mock …` or `ActionExecutor(mock=True)` | No |
| Real | default; device selected via `ANDROID_SERIAL` or auto-detect | Yes |

```bash
pytest                 # mock / unit only
pytest -m android      # real device, skipped if none connected
python scripts/run_demo.py --mock
python scripts/run_demo.py --apk path/to/app.apk
```

## What Member 3 and Member 4 consume

Member 3 (Knowledge Engine): each observation JSON + referenced screenshot + UI XML. Do not expect a Knowledge Pack from this module (`schemas/knowledge_pack.schema.json` is a placeholder).

Member 4 (Dashboard): glob `data/observations/*.json` for a timeline; show `screenshot_path`, `screen_id`, `elements`, and `caused_by_action_id`.

## Samples committed for handoff

* `data/sample/action_tap.json`
* `data/sample/action_type.json`
* `data/sample/action_scroll.json`
* `data/sample/action_back.json`
* `data/sample/observation.json`
* `data/screenshots/sample_observation.png`
* `data/ui_trees/sample_observation.xml`
