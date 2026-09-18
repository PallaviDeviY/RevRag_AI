import os
import json
import mimetypes

from dotenv import load_dotenv
from google import genai
from google.genai import types


# ============================================================
# LOAD ENVIRONMENT VARIABLES
# ============================================================

load_dotenv()


# ============================================================
# CONFIGURATION
# ============================================================

API_KEY = os.getenv("GEMINI_API_KEY")
MODEL_NAME = os.getenv("MODEL_NAME", "gemini-3.8-flash")

FALLBACK_MODEL = "gemini-3.5-flash-lite"


# ============================================================
# VALIDATE API KEY
# ============================================================

if not API_KEY:
    raise ValueError(
        "GEMINI_API_KEY is not set. "
        "Please add your Gemini API key to the .env file."
    )


# ============================================================
# GEMINI CLIENT
# ============================================================

client = genai.Client(api_key=API_KEY)


# ============================================================
# BASIC LLM FUNCTION
# ============================================================

def ask_llm(prompt: str) -> str:
    try:
        response = client.models.generate_content(
            model=MODEL_NAME,
            contents=prompt,
        )
        return response.text

    except Exception as primary_error:
        print(f"\nPrimary model failed: {MODEL_NAME}")
        print(f"Reason: {primary_error}")
        print(f"Trying fallback model: {FALLBACK_MODEL}\n")

        response = client.models.generate_content(
            model=FALLBACK_MODEL,
            contents=prompt,
        )
        return response.text

# ============================================================
# ANALYZE OBSERVATION WITH VISION
# ============================================================

def analyze_observation_with_vision(
    observation: dict,
) -> str:
    """
    Analyze an Android Observation using both:

        1. Observation JSON
        2. Screenshot referenced by screenshot_path

    The screenshot path comes directly from the Observation.
    """

    # --------------------------------------------------------
    # Get screenshot path from Observation
    # --------------------------------------------------------

    image_path = observation.get("screenshot_path")

    if not image_path:
        raise ValueError(
            "Observation does not contain 'screenshot_path'."
        )

    # --------------------------------------------------------
    # Convert Observation to readable JSON
    # --------------------------------------------------------

    observation_json = json.dumps(
        observation,
        indent=2
    )

    # --------------------------------------------------------
    # Build Vision prompt
    # --------------------------------------------------------

    prompt = f"""
You are the visual understanding component of an
autonomous Android application explorer.

You are given:

1. An Observation JSON describing the Android UI.
2. The actual screenshot of that observation.

Analyze BOTH sources together.

Your task is to understand the current screen.

Identify:

1. Overall screen purpose
2. Main visible text
3. Buttons and interactive controls
4. Input fields
5. Important visual components
6. Layout structure
7. Important colors or visual design details
8. Any visible UI elements that may not be represented
   clearly in the Observation JSON

Do not invent elements that are not visible.

Observation JSON:

{observation_json}
"""

    # --------------------------------------------------------
    # Send Observation + Screenshot to Gemini
    # --------------------------------------------------------

    return ask_llm_with_image(
        prompt=prompt,
        image_path=image_path,
    )

# ============================================================
# GEMINI VISION FUNCTION
# ============================================================

def ask_llm_with_image(prompt: str, image_path: str) -> str:
    from PIL import Image

    image = Image.open(image_path)

    try:
        response = client.models.generate_content(
            model=MODEL_NAME,
            contents=[
                prompt,
                image,
            ],
        )

        return response.text

    except Exception as primary_error:
        print(f"\nPrimary vision model failed: {MODEL_NAME}")
        print(f"Reason: {primary_error}")
        print(f"Trying fallback vision model: {FALLBACK_MODEL}\n")

        response = client.models.generate_content(
            model=FALLBACK_MODEL,
            contents=[
                prompt,
                image,
            ],
        )

        return response.text


# ============================================================
# LOAD OBSERVATION
# ============================================================

def load_observation(path: str) -> dict:
    """
    Load an Observation JSON file.
    """

    with open(path, "r", encoding="utf-8") as file:
        return json.load(file)


# ============================================================
# BUILD ACTION DECISION PROMPT
# ============================================================

def build_action_prompt(observation: dict) -> str:
    """
    Build a prompt asking Gemini to choose the next action.
    """

    observation_json = json.dumps(
        observation,
        indent=2
    )

    prompt = f"""
You are the AI decision-making brain of an autonomous
Android application explorer.

You are given the current Observation JSON from an Android app.

Your task is to choose ONE useful next action for exploration.

Rules:

1. Only choose an element that exists in the Observation JSON.
2. Use the exact element_id from the Observation JSON.
3. The action_type must be one of:
   - "tap"
   - "type"
4. Use "tap" for an interactive button or clickable control.
5. Use "type" for an EditText/input field.
6. Do not invent elements.
7. Do not invent element IDs.
8. Do not include bounds.
9. Do not include explanations.
10. Return ONLY valid JSON.

Return exactly this structure:

{{
  "element_id": "element_000000",
  "action_type": "tap"
}}

Current Observation JSON:

{observation_json}
"""

    return prompt


# ============================================================
# ASK GEMINI FOR NEXT ACTION
# ============================================================

def get_llm_action(observation: dict) -> dict:
    """
    Ask Gemini to select the next action and parse
    its response into a Python dictionary.
    """

    prompt = build_action_prompt(observation)

    response_text = ask_llm(prompt).strip()

    # --------------------------------------------------------
    # Remove Markdown code fences if Gemini adds them
    # --------------------------------------------------------

    if response_text.startswith("```"):
        lines = response_text.splitlines()

        if lines and lines[0].startswith("```"):
            lines = lines[1:]

        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]

        response_text = "\n".join(lines).strip()

    # --------------------------------------------------------
    # Convert JSON text into Python dictionary
    # --------------------------------------------------------

    try:
        action = json.loads(response_text)
    except json.JSONDecodeError as error:
        raise ValueError(
            f"Gemini did not return valid JSON.\n"
            f"Gemini response:\n{response_text}"
        ) from error

    # --------------------------------------------------------
    # Basic structure validation
    # --------------------------------------------------------

    if not isinstance(action, dict):
        raise ValueError("Gemini action must be a JSON object.")

    if "element_id" not in action:
        raise ValueError("Gemini action is missing 'element_id'.")

    if "action_type" not in action:
        raise ValueError("Gemini action is missing 'action_type'.")

    if action["action_type"] not in {"tap", "type"}:
        raise ValueError(
            f"Unsupported action_type: {action['action_type']}"
        )

    return action

# ============================================================
# VALIDATE GEMINI ACTION AGAINST OBSERVATION
# ============================================================

def validate_llm_action(action: dict, observation: dict) -> dict:
    """
    Validate Gemini's proposed action against the actual
    elements present in the Observation JSON.

    Gemini is allowed to choose:
        - element_id
        - action_type

    Python verifies:
        - element exists
        - element is enabled
        - action is compatible with the element
        - bounds come from the trusted observation
    """

    element_id = action["element_id"]
    action_type = action["action_type"]

    # --------------------------------------------------------
    # Find the element in the observation
    # --------------------------------------------------------

    matching_element = None

    for element in observation.get("elements", []):
        if element.get("element_id") == element_id:
            matching_element = element
            break

    # --------------------------------------------------------
    # Element must exist
    # --------------------------------------------------------

    if matching_element is None:
        raise ValueError(
            f"Gemini selected unknown element: {element_id}"
        )

    # --------------------------------------------------------
    # Element must be enabled
    # --------------------------------------------------------

    if not matching_element.get("enabled", False):
        raise ValueError(
            f"Gemini selected disabled element: {element_id}"
        )

    # --------------------------------------------------------
    # Validate action type
    # --------------------------------------------------------

    if action_type == "tap":

        if not matching_element.get("clickable", False):
            raise ValueError(
                f"Element {element_id} is not clickable."
            )

    elif action_type == "type":

        element_type = matching_element.get("type", "")

        if element_type != "android.widget.EditText":
            raise ValueError(
                f"Element {element_id} is not an EditText."
            )

    else:

        raise ValueError(
            f"Unsupported action type: {action_type}"
        )

    # --------------------------------------------------------
    # Create trusted action
    # --------------------------------------------------------

    validated_action = {
        "action_id": "action_llm_000001",
        "action_type": action_type,
        "element_id": element_id,
        "bounds": matching_element["bounds"],
    }

    return validated_action


# ============================================================
# VISION TEST
# ============================================================

def test_vision():

    image_path = "screenshots/test_screen.png"

    prompt = """
You are analyzing a screenshot of an Android application.

Describe the visible interface briefly.

Identify:
1. Main visible text
2. Buttons
3. Input fields
4. Important visual components
5. Overall screen purpose

Do not invent elements that are not visible.
"""

    result = ask_llm_with_image(
        prompt=prompt,
        image_path=image_path,
    )

    print("\n")
    print("=" * 60)
    print("GEMINI VISION RESPONSE")
    print("=" * 60)

    print(result)


if __name__ == "__main__":

    observation = load_observation(
        "data/sample/sample_observation.json"
    )

    result = analyze_observation_with_vision(
        observation
    )

    print("\n")
    print("=" * 60)
    print("OBSERVATION + VISION RESPONSE")
    print("=" * 60)

    print(result)