import json

from ai.element_understanding import understand_element


# ============================================================
# CREATE ACTION CANDIDATE
# ============================================================

def create_action_candidate(element, action_type):
    """
    Create a description of one possible action.

    This function does not execute the action.
    It only creates a candidate for the planner.
    """

    return {
        "element_id": element.get("element_id"),
        "action_type": action_type,
        "bounds": element.get("bounds"),
        "element_type": element.get("type"),
        "text": element.get("text"),
        "content_description": element.get(
            "content_description"
        ),
        "semantic_role": element.get(
            "semantic_role"
        ),
        "purpose": element.get(
            "purpose"
        )
    }


# ============================================================
# DETECT ACTIONS FOR ONE ELEMENT
# ============================================================

def detect_element_actions(element):
    """
    Understand one element and determine its
    possible interactions.
    """

    understood_element = understand_element(element)

    possible_actions = understood_element.get(
        "possible_actions",
        []
    )

    candidates = []

    for action_type in possible_actions:

        candidate = create_action_candidate(
            understood_element,
            action_type
        )

        candidates.append(candidate)

    return candidates


# ============================================================
# DETECT ACTIONS FOR COMPLETE SCREEN
# ============================================================

def detect_candidate_actions(observation):
    """
    Detect all possible actions available on
    the current screen.
    """

    elements = observation.get(
        "elements",
        []
    )

    candidates = []

    for element in elements:

        # ----------------------------------------------------
        # Ignore disabled elements
        # ----------------------------------------------------

        if element.get("enabled") is False:
            continue

        element_candidates = detect_element_actions(
            element
        )

        candidates.extend(
            element_candidates
        )

    return candidates


# ============================================================
# CREATE SIMPLE SUMMARY
# ============================================================

def summarize_candidates(candidates):
    """
    Create a compact summary of candidate actions.
    """

    summary = []

    for candidate in candidates:

        summary.append(
            {
                "element_id": candidate.get(
                    "element_id"
                ),
                "action_type": candidate.get(
                    "action_type"
                ),
                "purpose": candidate.get(
                    "purpose"
                )
            }
        )

    return summary


# ============================================================
# TEST
# ============================================================

if __name__ == "__main__":

    # --------------------------------------------------------
    # Load the real team Observation format
    # --------------------------------------------------------

    with open(
        "data/sample/sample_observation.json",
        "r",
        encoding="utf-8"
    ) as file:

        observation = json.load(file)

    # --------------------------------------------------------
    # Detect candidate actions
    # --------------------------------------------------------

    candidates = detect_candidate_actions(
        observation
    )

    # --------------------------------------------------------
    # Print complete candidate information
    # --------------------------------------------------------

    print("\n" + "=" * 60)
    print("CANDIDATE ACTIONS")
    print("=" * 60)

    print(
        json.dumps(
            candidates,
            indent=2,
            ensure_ascii=False
        )
    )

    # --------------------------------------------------------
    # Print compact summary
    # --------------------------------------------------------

    print("\n" + "=" * 60)
    print("ACTION SUMMARY")
    print("=" * 60)

    print(
        json.dumps(
            summarize_candidates(candidates),
            indent=2,
            ensure_ascii=False
        )
    )