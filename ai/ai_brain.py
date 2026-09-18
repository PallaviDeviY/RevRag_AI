import json

from ai.llm_client import (
    load_observation,
    analyze_observation_with_vision,
    get_llm_action,
    validate_llm_action,
)


# ============================================================
# AI BRAIN
# ============================================================

class AIBrain:
    """
    Combined AI brain for autonomous Android exploration.

    Flow:

        Observation
             ↓
        Optional Vision
             ↓
        Gemini Action Decision
             ↓
        Python Validation
             ↓
        Local Fallback if Gemini quota is exhausted
    """

    def __init__(self):
        self.decision_count = 0

        # Vision is expensive in terms of API usage.
        # We therefore do not call it on every iteration.
        self.use_vision = False

    # ========================================================
    # LOCAL FALLBACK ACTION
    # ========================================================

    def _fallback_action(self, observation: dict) -> dict:
        """
        Select a safe action without using Gemini.

        This keeps autonomous exploration running even when
        the Gemini API quota is exhausted.
        """

        elements = observation.get("elements", [])

        # ----------------------------------------------------
        # Priority 1: useful text fields
        # ----------------------------------------------------

        for element in elements:

            if not element.get("enabled", False):
                continue

            if not element.get("clickable", False):
                continue

            element_id = element.get("element_id")
            element_type = (
                element.get("type") or ""
            ).lower()

            text = (
                element.get("text") or ""
            ).lower()

            description = (
                element.get("content_description") or ""
            ).lower()

            resource_id = (
                element.get("resource_id") or ""
            ).lower()

            combined = (
                text
                + " "
                + description
                + " "
                + resource_id
            )

            # Avoid obvious system/navigation elements.
            if any(
                word in combined
                for word in [
                    "back",
                    "home",
                    "navigation",
                    "toolbar",
                ]
            ):
                continue

            # ------------------------------------------------
            # EditText
            # ------------------------------------------------

            if "edittext" in element_type:
                return {
                    "action_id": (
                        f"action_fallback_"
                        f"{self.decision_count:06d}"
                    ),
                    "action_type": "tap",
                    "element_id": element_id,
                    "bounds": element["bounds"],
                }

            # ------------------------------------------------
            # Buttons with useful actions
            # ------------------------------------------------

            if any(
                word in combined
                for word in [
                    "continue",
                    "next",
                    "login",
                    "sign in",
                    "submit",
                    "allow",
                    "accept",
                    "get started",
                    "done",
                    "save",
                    "yes",
                    "ok",
                ]
            ):
                return {
                    "action_id": (
                        f"action_fallback_"
                        f"{self.decision_count:06d}"
                    ),
                    "action_type": "tap",
                    "element_id": element_id,
                    "bounds": element["bounds"],
                }

        # ----------------------------------------------------
        # Priority 2: any safe clickable element
        # ----------------------------------------------------

        for element in elements:

            if not element.get("enabled", False):
                continue

            if not element.get("clickable", False):
                continue

            bounds = element.get("bounds")

            if not bounds:
                continue

            return {
                "action_id": (
                    f"action_fallback_"
                    f"{self.decision_count:06d}"
                ),
                "action_type": "tap",
                "element_id": element.get("element_id"),
                "bounds": bounds,
            }

        # ----------------------------------------------------
        # No action available
        # ----------------------------------------------------

        return None

    # ========================================================
    # GENERATE DECISION
    # ========================================================

    def decide(self, observation: dict) -> dict:
        """
        Analyze an Observation and produce a validated action.

        Gemini is attempted first.

        If Gemini is unavailable or quota is exhausted,
        a local safe fallback action is generated.
        """

        self.decision_count += 1

        # ----------------------------------------------------
        # STEP 1: Optional Gemini Vision
        # ----------------------------------------------------

        vision_result = (
            "Vision skipped to reduce API usage."
        )

        if self.use_vision:

            try:

                vision_result = (
                    analyze_observation_with_vision(
                        observation
                    )
                )

            except Exception as error:

                print(
                    "\n[AI] Vision unavailable."
                )

                print(
                    "[AI] Continuing without Vision."
                )

                vision_result = (
                    f"Vision unavailable: {error}"
                )

        # ----------------------------------------------------
        # STEP 2: Gemini Action Decision
        # ----------------------------------------------------

        llm_action = None
        validated_action = None

        try:

            print(
                "\n[AI] Asking Gemini for action..."
            )

            llm_action = get_llm_action(
                observation
            )

            # ------------------------------------------------
            # STEP 3: Python Safety Validation
            # ------------------------------------------------

            validated_action = (
                validate_llm_action(
                    llm_action,
                    observation
                )
            )

            print(
                "[AI] Gemini action validated."
            )

        except Exception as error:

            # ------------------------------------------------
            # Gemini failed / quota exhausted
            # ------------------------------------------------

            print(
                "\n[AI] Gemini unavailable."
            )

            print(
                "[AI] Using LOCAL FALLBACK action."
            )

            print(
                "[AI] Reason:",
                error
            )

            # ------------------------------------------------
            # Local fallback
            # ------------------------------------------------

            validated_action = (
                self._fallback_action(
                    observation
                )
            )

            if validated_action is None:

                raise RuntimeError(
                    "No safe action available "
                    "from Gemini or local fallback."
                )

            llm_action = {
                "source": "local_fallback",
                "action_type": validated_action[
                    "action_type"
                ],
                "element_id": validated_action[
                    "element_id"
                ],
            }

        # ----------------------------------------------------
        # Return complete AI decision
        # ----------------------------------------------------

        return {

            "decision_id": (
                f"decision_"
                f"{self.decision_count:06d}"
            ),

            "screen_id": observation.get(
                "screen_id"
            ),

            "observation_id": observation.get(
                "observation_id"
            ),

            "vision_understanding": vision_result,

            "llm_proposal": llm_action,

            "validated_action": validated_action,
        }


# ============================================================
# TEST
# ============================================================

if __name__ == "__main__":

    print("\n")
    print("=" * 60)
    print("AI BRAIN TEST")
    print("=" * 60)

    # --------------------------------------------------------
    # Load sample observation
    # --------------------------------------------------------

    observation = load_observation(
        "data/sample/sample_observation.json"
    )

    # --------------------------------------------------------
    # Create AI Brain
    # --------------------------------------------------------

    brain = AIBrain()

    # --------------------------------------------------------
    # Ask AI Brain to make a decision
    # --------------------------------------------------------

    result = brain.decide(
        observation
    )

    # --------------------------------------------------------
    # Display result
    # --------------------------------------------------------

    print("\nDecision ID:")
    print(result["decision_id"])

    print("\nScreen ID:")
    print(result["screen_id"])

    print("\nObservation ID:")
    print(result["observation_id"])

    print("\n")
    print("=" * 60)
    print("VISION UNDERSTANDING")
    print("=" * 60)

    print(
        result["vision_understanding"]
    )

    print("\n")
    print("=" * 60)
    print("GEMINI / FALLBACK ACTION")
    print("=" * 60)

    print(
        json.dumps(
            result["llm_proposal"],
            indent=2
        )
    )

    print("\n")
    print("=" * 60)
    print("VALIDATED ACTION")
    print("=" * 60)

    print(
        json.dumps(
            result["validated_action"],
            indent=2
        )
    )

    print("\n")
    print("=" * 60)
    print("AI BRAIN TEST COMPLETE")
    print("=" * 60)