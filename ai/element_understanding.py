import json


# ============================================================
# TEXT EXTRACTION
# ============================================================

def get_element_text(element):
    """
    Collect the useful textual information available
    for an element.
    """

    text = element.get("text") or ""
    content_description = element.get("content_description") or ""

    return f"{text} {content_description}".strip()


# ============================================================
# SEMANTIC ROLE
# ============================================================

def determine_semantic_role(element):
    """
    Determine the basic semantic role of an Android UI element.
    """

    element_type = (element.get("type") or "").lower()

    text = (element.get("text") or "").lower()
    content_description = (
        element.get("content_description") or ""
    ).lower()

    combined_text = f"{text} {content_description}"

    # --------------------------------------------------------
    # Buttons
    # --------------------------------------------------------

    if "button" in element_type:
        return "button"

    # --------------------------------------------------------
    # Text input
    # --------------------------------------------------------

    if "edittext" in element_type:

        if "password" in combined_text:
            return "password_input"

        if "username" in combined_text:
            return "username_input"

        if "email" in combined_text:
            return "email_input"

        return "text_input"

    # --------------------------------------------------------
    # Text
    # --------------------------------------------------------

    if "textview" in element_type:
        return "text"

    # --------------------------------------------------------
    # Scrollable element
    # --------------------------------------------------------

    if element.get("scrollable") is True:
        return "scrollable"

    # --------------------------------------------------------
    # Generic clickable element
    # --------------------------------------------------------

    if element.get("clickable") is True:
        return "clickable"

    return "other"


# ============================================================
# PURPOSE DETECTION
# ============================================================

def determine_purpose(element, semantic_role):
    """
    Determine the likely purpose of an element using
    its type and available text.
    """

    text = (element.get("text") or "").strip()
    description = (
        element.get("content_description") or ""
    ).strip()

    combined_text = f"{text} {description}".lower()

    # --------------------------------------------------------
    # Username
    # --------------------------------------------------------

    if semantic_role == "username_input":
        return "Allows the user to enter a username."

    # --------------------------------------------------------
    # Password
    # --------------------------------------------------------

    if semantic_role == "password_input":
        return "Allows the user to enter a password."

    # --------------------------------------------------------
    # Email
    # --------------------------------------------------------

    if semantic_role == "email_input":
        return "Allows the user to enter an email address."

    # --------------------------------------------------------
    # Generic input
    # --------------------------------------------------------

    if semantic_role == "text_input":
        return "Allows the user to enter text."

    # --------------------------------------------------------
    # Login
    # --------------------------------------------------------

    if semantic_role == "button":

        if any(
            keyword in combined_text
            for keyword in [
                "login",
                "log in",
                "sign in",
                "signin"
            ]
        ):
            return "Submits login or authentication information."

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
            return "Submits account registration information."

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
            return "Initiates a search operation."

    # --------------------------------------------------------
    # Back
    # --------------------------------------------------------

        if "back" in combined_text:
            return "Navigates back to the previous screen."

    # --------------------------------------------------------
    # Generic button
    # --------------------------------------------------------

        return "Triggers an action when selected."

    # --------------------------------------------------------
    # Scrollable
    # --------------------------------------------------------

    if semantic_role == "scrollable":
        return "Contains content that can be scrolled."

    # --------------------------------------------------------
    # Text
    # --------------------------------------------------------

    if semantic_role == "text":

        if text:
            return "Displays informational or interface text."

        return "Displays text information."

    # --------------------------------------------------------
    # Clickable
    # --------------------------------------------------------

    if semantic_role == "clickable":
        return "Provides an interactive action."

    return "Purpose could not be determined from the available information."


# ============================================================
# POSSIBLE ACTIONS
# ============================================================

def determine_possible_actions(element, semantic_role):
    """
    Determine which basic interactions may be possible
    for this element.

    This does NOT execute any action.
    """

    actions = []

    enabled = element.get("enabled", False)
    clickable = element.get("clickable", False)
    scrollable = element.get("scrollable", False)

    if not enabled:
        return actions

    # --------------------------------------------------------
    # Input fields
    # --------------------------------------------------------

    if semantic_role in [
        "username_input",
        "password_input",
        "email_input",
        "text_input"
    ]:

        actions.append("tap")
        actions.append("type")

    # --------------------------------------------------------
    # Buttons / clickable elements
    # --------------------------------------------------------

    elif semantic_role in [
        "button",
        "clickable"
    ]:

        if clickable:
            actions.append("tap")

    # --------------------------------------------------------
    # Scrollable elements
    # --------------------------------------------------------

    if scrollable:
        actions.append("scroll")

    return actions


# ============================================================
# COMPLETE ELEMENT UNDERSTANDING
# ============================================================

def understand_element(element):
    """
    Convert a raw Observation element into a structured
    semantic understanding.
    """

    semantic_role = determine_semantic_role(element)

    purpose = determine_purpose(
        element,
        semantic_role
    )

    possible_actions = determine_possible_actions(
        element,
        semantic_role
    )

    return {
        "element_id": element.get("element_id"),
        "type": element.get("type"),
        "text": element.get("text"),
        "content_description": element.get(
            "content_description"
        ),
        "resource_id": element.get("resource_id"),
        "clickable": element.get("clickable"),
        "enabled": element.get("enabled"),
        "scrollable": element.get("scrollable"),
        "bounds": element.get("bounds"),
        "semantic_role": semantic_role,
        "purpose": purpose,
        "possible_actions": possible_actions
    }


# ============================================================
# TESTING
# ============================================================

if __name__ == "__main__":

    # --------------------------------------------------------
    # Load sample observation
    # --------------------------------------------------------

    with open(
        "data/sample/sample_observation.json",
        "r",
        encoding="utf-8"
    ) as file:

        observation = json.load(file)

    # --------------------------------------------------------
    # Understand every element
    # --------------------------------------------------------

    elements = observation.get("elements", [])

    results = []

    for element in elements:

        result = understand_element(element)

        results.append(result)

    # --------------------------------------------------------
    # Display results
    # --------------------------------------------------------

    print("\n" + "=" * 60)
    print("ELEMENT UNDERSTANDING")
    print("=" * 60)

    print(
        json.dumps(
            results,
            indent=2,
            ensure_ascii=False
        )
    )