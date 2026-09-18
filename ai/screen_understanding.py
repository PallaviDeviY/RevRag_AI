import json


# ============================================================
# ELEMENT CLASSIFICATION
# ============================================================

def classify_element(element):
    """
    Classify an Android UI element using the fields
    provided by the Observation schema.
    """

    element_type = (element.get("type") or "").lower()
    text = (element.get("text") or "").lower()
    content_description = (
        element.get("content_description") or ""
    ).lower()

    combined_text = f"{text} {content_description}"

    # --------------------------------------------------------
    # Input fields
    # --------------------------------------------------------

    if "edittext" in element_type:
        return "input"

    # --------------------------------------------------------
    # Buttons
    # --------------------------------------------------------

    if "button" in element_type:
        return "button"

    # --------------------------------------------------------
    # Text
    # --------------------------------------------------------

    if "textview" in element_type:
        return "text"

    # --------------------------------------------------------
    # Other clickable elements
    # --------------------------------------------------------

    if element.get("clickable") is True:
        return "clickable"

    # --------------------------------------------------------
    # Scrollable elements
    # --------------------------------------------------------

    if element.get("scrollable") is True:
        return "scrollable"

    return "other"


# ============================================================
# SCREEN PURPOSE DETECTION
# ============================================================

def detect_screen_purpose(elements):
    """
    Estimate the purpose of the screen using visible
    text, content descriptions and Android element types.

    This is a basic deterministic layer.
    LLM-based reasoning will be added later.
    """

    all_text = []

    for element in elements:

        text = element.get("text") or ""
        description = element.get("content_description") or ""

        if text:
            all_text.append(text.lower())

        if description:
            all_text.append(description.lower())

    combined_text = " ".join(all_text)

    # --------------------------------------------------------
    # Login / authentication
    # --------------------------------------------------------

    if any(
        keyword in combined_text
        for keyword in [
            "login",
            "log in",
            "sign in",
            "signin"
        ]
    ):
        return {
            "screen_name": "Login Screen",
            "purpose": "Allows the user to authenticate or sign in."
        }

    # --------------------------------------------------------
    # Registration
    # --------------------------------------------------------

    if any(
        keyword in combined_text
        for keyword in [
            "register",
            "sign up",
            "signup",
            "create account"
        ]
    ):
        return {
            "screen_name": "Registration Screen",
            "purpose": "Allows the user to create an account."
        }

    # --------------------------------------------------------
    # Search
    # --------------------------------------------------------

    if any(
        keyword in combined_text
        for keyword in [
            "search",
            "find"
        ]
    ):
        return {
            "screen_name": "Search Screen",
            "purpose": "Allows the user to search for information."
        }

    # --------------------------------------------------------
    # Profile
    # --------------------------------------------------------

    if any(
        keyword in combined_text
        for keyword in [
            "profile",
            "account",
            "my account"
        ]
    ):
        return {
            "screen_name": "Profile Screen",
            "purpose": "Allows the user to view or manage their profile."
        }

    # --------------------------------------------------------
    # Home
    # --------------------------------------------------------

    if any(
        keyword in combined_text
        for keyword in [
            "home",
            "dashboard"
        ]
    ):
        return {
            "screen_name": "Home Screen",
            "purpose": "Provides the main entry point or overview of the application."
        }

    # --------------------------------------------------------
    # Unknown
    # --------------------------------------------------------

    return {
        "screen_name": "Unknown Screen",
        "purpose": "The screen purpose could not be determined from the available UI information."
    }


# ============================================================
# SCREEN UNDERSTANDING
# ============================================================

def understand_screen(observation):
    """
    Convert an Observation JSON object into a structured
    screen understanding result.
    """

    # --------------------------------------------------------
    # Read screen-level information
    # --------------------------------------------------------

    screen_id = observation.get("screen_id")

    package_name = observation.get("package_name")

    activity = observation.get("activity")

    # --------------------------------------------------------
    # IMPORTANT:
    # The real Observation schema uses "elements".
    # --------------------------------------------------------

    elements = observation.get("elements", [])

    # --------------------------------------------------------
    # Categorize elements
    # --------------------------------------------------------

    buttons = []
    inputs = []
    texts = []
    clickable_elements = []
    scrollable_elements = []
    other_elements = []

    for element in elements:

        category = classify_element(element)

        if category == "button":
            buttons.append(element)

        elif category == "input":
            inputs.append(element)

        elif category == "text":
            texts.append(element)

        elif category == "clickable":
            clickable_elements.append(element)

        elif category == "scrollable":
            scrollable_elements.append(element)

        else:
            other_elements.append(element)

    # --------------------------------------------------------
    # Determine screen purpose
    # --------------------------------------------------------

    screen_info = detect_screen_purpose(elements)

    # --------------------------------------------------------
    # Return structured result
    # --------------------------------------------------------

    return {
        "screen_id": screen_id,
        "package_name": package_name,
        "activity": activity,
        "screen_name": screen_info["screen_name"],
        "purpose": screen_info["purpose"],
        "buttons": buttons,
        "inputs": inputs,
        "texts": texts,
        "clickable_elements": clickable_elements,
        "scrollable_elements": scrollable_elements,
        "other_elements": other_elements
    }


# ============================================================
# TESTING
# ============================================================

if __name__ == "__main__":

    # --------------------------------------------------------
    # Load the sample Observation
    # --------------------------------------------------------

    with open(
        "data/sample/sample_observation.json",
        "r",
        encoding="utf-8"
    ) as file:

        observation = json.load(file)

    # --------------------------------------------------------
    # Run screen understanding
    # --------------------------------------------------------

    result = understand_screen(observation)

    # --------------------------------------------------------
    # Display result
    # --------------------------------------------------------

    print("\n" + "=" * 60)
    print("SCREEN UNDERSTANDING")
    print("=" * 60)

    print(
        json.dumps(
            result,
            indent=2,
            ensure_ascii=False
        )
    )