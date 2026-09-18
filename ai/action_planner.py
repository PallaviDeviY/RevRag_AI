import json

from ai.action_detection import detect_candidate_actions


# ============================================================
# ACTION PRIORITY
# ============================================================

def calculate_action_priority(candidate):
    """
    Calculate a deterministic priority for an action.

    Higher score = more useful as the next exploration action.

    This is the initial planning layer.
    Later, LLM reasoning can be added on top of this.
    """

    action_type = candidate.get("action_type")
    semantic_role = candidate.get("semantic_role")
    text = (
        candidate.get("text") or ""
    ).lower()

    purpose = (
        candidate.get("purpose") or ""
    ).lower()

    score = 0

    # --------------------------------------------------------
    # Disabled elements should never be selected
    # --------------------------------------------------------

    if candidate.get("enabled") is False:
        return -1000

    # --------------------------------------------------------
    # Input fields
    # --------------------------------------------------------

    if semantic_role == "username_input":

        if action_type == "type":
            score += 100

        elif action_type == "tap":
            score += 70

    elif semantic_role == "password_input":

        if action_type == "type":
            score += 90

        elif action_type == "tap":
            score += 60

    elif semantic_role == "email_input":

        if action_type == "type":
            score += 90

        elif action_type == "tap":
            score += 60

    elif semantic_role == "text_input":

        if action_type == "type":
            score += 80

        elif action_type == "tap":
            score += 50

    # --------------------------------------------------------
    # Buttons
    # --------------------------------------------------------

    elif semantic_role == "button":

        # Login should normally happen after required
        # input fields have been handled.
        if any(
            keyword in text
            for keyword in [
                "login",
                "log in",
                "sign in",
                "signin"
            ]
        ):

            score += 30

        else:
            score += 40

    # --------------------------------------------------------
    # Generic clickable element
    # --------------------------------------------------------

    elif semantic_role == "clickable":

        score += 20

    # --------------------------------------------------------
    # Scrollable content
    # --------------------------------------------------------

    if action_type == "scroll":

        score += 10

    # --------------------------------------------------------
    # Small purpose-based bonus
    # --------------------------------------------------------

    if "enter" in purpose:

        if action_type == "type":
            score += 10

    return score


# ============================================================
# RANK CANDIDATE ACTIONS
# ============================================================

def rank_candidates(candidates):
    """
    Rank candidate actions from highest to lowest priority.
    """

    ranked = []

    for candidate in candidates:

        score = calculate_action_priority(
            candidate
        )

        candidate_with_score = dict(candidate)

        candidate_with_score["priority_score"] = score

        ranked.append(
            candidate_with_score
        )

    ranked.sort(
        key=lambda item: item["priority_score"],
        reverse=True
    )

    return ranked


# ============================================================
# CHOOSE NEXT ACTION
# ============================================================

def choose_next_action(candidates):
    """
    Select the highest-priority candidate.

    Returns None if there are no valid candidates.
    """

    if not candidates:
        return None

    ranked_candidates = rank_candidates(
        candidates
    )

    best_candidate = ranked_candidates[0]

    return best_candidate


# ============================================================
# COMPLETE PLANNER
# ============================================================

def plan_next_action(observation):
    """
    Detect candidate actions and select the most useful
    next action for the current screen.
    """

    # --------------------------------------------------------
    # Step 1: Detect possible actions
    # --------------------------------------------------------

    candidates = detect_candidate_actions(
        observation
    )

    # --------------------------------------------------------
    # Step 2: Rank candidates
    # --------------------------------------------------------

    ranked_candidates = rank_candidates(
        candidates
    )

    # --------------------------------------------------------
    # Step 3: Select best candidate
    # --------------------------------------------------------

    selected_action = None

    if ranked_candidates:
        selected_action = ranked_candidates[0]

    # --------------------------------------------------------
    # Return planning result
    # --------------------------------------------------------

    return {
        "screen_id": observation.get(
            "screen_id"
        ),
        "candidate_count": len(
            candidates
        ),
        "ranked_candidates": ranked_candidates,
        "selected_action": selected_action
    }


# ============================================================
# TEST
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
    # Plan next action
    # --------------------------------------------------------

    result = plan_next_action(
        observation
    )

    # --------------------------------------------------------
    # Display result
    # --------------------------------------------------------

    print("\n" + "=" * 60)
    print("ACTION PLANNER")
    print("=" * 60)

    print(
        json.dumps(
            result,
            indent=2,
            ensure_ascii=False
        )
    )

    # --------------------------------------------------------
    # Display selected action separately
    # --------------------------------------------------------

    print("\n" + "=" * 60)
    print("SELECTED NEXT ACTION")
    print("=" * 60)

    print(
        json.dumps(
            result["selected_action"],
            indent=2,
            ensure_ascii=False
        )
    )