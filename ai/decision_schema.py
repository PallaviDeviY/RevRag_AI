from typing import Dict

from pydantic import BaseModel, ConfigDict, Field


# ============================================================
# BOUNDS
# ============================================================

class ActionBounds(BaseModel):
    """
    Bounds of the target UI element.

    These coordinates come from the team's Observation schema.
    """

    model_config = ConfigDict(extra="forbid")

    left: int
    top: int
    right: int
    bottom: int


# ============================================================
# FINAL ACTION
# ============================================================

class Action(BaseModel):
    """
    Exact Action structure sent from the AI Brain
    to the Android Controller.

    This follows the team's action.schema.json example.
    """

    model_config = ConfigDict(extra="forbid")

    action_id: str
    action_type: str
    element_id: str
    bounds: ActionBounds


# ============================================================
# CONVERT CANDIDATE INTO FINAL ACTION
# ============================================================

def build_action(candidate):
    """
    Convert an internal planner candidate into the exact
    Action JSON structure used by the team.

    Internal fields such as purpose, semantic_role and
    priority_score are intentionally removed.
    """

    action = Action(
        action_id=candidate.get(
            "action_id",
            "action_000001"
        ),
        action_type=candidate.get(
            "action_type"
        ),
        element_id=candidate.get(
            "element_id"
        ),
        bounds=ActionBounds(
            **candidate.get("bounds")
        )
    )

    return action


# ============================================================
# ACTION SAFETY
# ============================================================

def validate_action_safety(
    action,
    observation
):
    """
    Validate that an action is safe to send to the
    Android controller.

    Returns:

        (True, "Action is safe.")

    or:

        (False, "Reason for rejection")
    """

    if action is None:
        return False, "Action is missing."

    # --------------------------------------------------------
    # Get element list from Observation
    # --------------------------------------------------------

    elements = observation.get(
        "elements",
        []
    )

    # --------------------------------------------------------
    # Find target element
    # --------------------------------------------------------

    target_element = None

    for element in elements:

        if (
            element.get("element_id")
            == action.element_id
        ):
            target_element = element
            break

    # --------------------------------------------------------
    # Element must exist
    # --------------------------------------------------------

    if target_element is None:

        return (
            False,
            "Target element does not exist in the current observation."
        )

    # --------------------------------------------------------
    # Element must be enabled
    # --------------------------------------------------------

    if target_element.get("enabled") is False:

        return (
            False,
            "Target element is disabled."
        )

    # --------------------------------------------------------
    # Validate bounds
    # --------------------------------------------------------

    bounds = action.bounds

    if bounds.left < 0:
        return False, "Invalid left bound."

    if bounds.top < 0:
        return False, "Invalid top bound."

    if bounds.right <= bounds.left:
        return False, "Invalid horizontal bounds."

    if bounds.bottom <= bounds.top:
        return False, "Invalid vertical bounds."

    # --------------------------------------------------------
    # Make sure the action targets the same bounds
    # as the observed element.
    # --------------------------------------------------------

    observed_bounds = target_element.get(
        "bounds"
    )

    if not observed_bounds:
        return (
            False,
            "Target element has no bounds."
        )

    if (
        bounds.left != observed_bounds.get("left")
        or
        bounds.top != observed_bounds.get("top")
        or
        bounds.right != observed_bounds.get("right")
        or
        bounds.bottom != observed_bounds.get("bottom")
    ):

        return (
            False,
            "Action bounds do not match the observed element bounds."
        )

    # --------------------------------------------------------
    # Action-specific safety
    # --------------------------------------------------------

    action_type = action.action_type.lower()

    clickable = target_element.get(
        "clickable"
    )

    element_type = (
        target_element.get("type") or ""
    ).lower()

    # --------------------------------------------------------
    # TAP
    # --------------------------------------------------------

    if action_type == "tap":

        if clickable is not True:

            return (
                False,
                "Tap action targets an element that is not clickable."
            )

    # --------------------------------------------------------
    # TYPE
    # --------------------------------------------------------

    if action_type == "type":

        if "edittext" not in element_type:

            return (
                False,
                "Type action targets an element that is not an EditText."
            )

    # --------------------------------------------------------
    # All safety checks passed
    # --------------------------------------------------------

    return True, "Action is safe."


# ============================================================
# TEST
# ============================================================

if __name__ == "__main__":

    import json

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
    # Create a valid test candidate
    # --------------------------------------------------------

    candidate = {
        "action_id": "action_000001",
        "action_type": "tap",
        "element_id": "element_000004",
        "bounds": {
            "left": 100,
            "top": 420,
            "right": 500,
            "bottom": 500
        }
    }

    # --------------------------------------------------------
    # Convert to final Action
    # --------------------------------------------------------

    action = build_action(
        candidate
    )

    # --------------------------------------------------------
    # Validate safety
    # --------------------------------------------------------

    is_safe, message = validate_action_safety(
        action,
        observation
    )

    # --------------------------------------------------------
    # Display result
    # --------------------------------------------------------

    print("\n" + "=" * 60)
    print("ACTION SAFETY TEST")
    print("=" * 60)

    print(
        "Safe:",
        is_safe
    )

    print(
        "Message:",
        message
    )

    # --------------------------------------------------------
    # Display exact Action JSON
    # --------------------------------------------------------

    print("\n" + "=" * 60)
    print("FINAL ACTION JSON")
    print("=" * 60)

    print(
        json.dumps(
            action.model_dump(),
            indent=2
        )
    )