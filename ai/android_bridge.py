from android.actions import ActionExecutor
from ai.ai_brain import AIBrain


class AIAndroidBridge:
    """
    Bridge between the AI Exploration Agent and
    Pallavi's Android ActionExecutor.

    Flow:

        Android Observation
                ↓
        Normalize Observation
                ↓
             AI Brain
                ↓
          Validated Action
                ↓
        Android Bridge
                ↓
         ActionExecutor
                ↓
          Android App
    """

    def __init__(self):
        self.ai_brain = AIBrain()
        self.executor = ActionExecutor()

    # ============================================================
    # OBSERVATION NORMALIZATION
    # ============================================================

    def _normalize_observation(self, observation) -> dict:
        """
        Convert the Android Observation object into the
        dictionary format expected by AIBrain/Gemini.

        Handles:
        - Observation objects
        - UIElement objects
        - Bounds objects
        """

        # --------------------------------------------------------
        # Already a normal dictionary
        # --------------------------------------------------------

        if isinstance(observation, dict):
            normalized = dict(observation)

        else:
            # ----------------------------------------------------
            # Convert Observation object to dictionary
            # ----------------------------------------------------

            normalized = {
                "observation_id": getattr(
                    observation,
                    "observation_id",
                    None
                ),

                "screen_id": getattr(
                    observation,
                    "screen_id",
                    None
                ),

                "timestamp": getattr(
                    observation,
                    "timestamp",
                    None
                ),

                "package_name": getattr(
                    observation,
                    "package_name",
                    None
                ),

                "activity": getattr(
                    observation,
                    "activity",
                    None
                ),

                "screenshot_path": getattr(
                    observation,
                    "screenshot_path",
                    None
                ),

                "ui_tree_path": getattr(
                    observation,
                    "ui_tree_path",
                    None
                ),

                "elements": getattr(
                    observation,
                    "elements",
                    []
                ),
            }

        # ========================================================
        # NORMALIZE ELEMENTS
        # ========================================================

        normalized_elements = []

        for element in normalized.get("elements", []):

            # ----------------------------------------------------
            # If element is already a dictionary
            # ----------------------------------------------------

            if isinstance(element, dict):
                element_data = dict(element)

            else:
                # ------------------------------------------------
                # Convert UIElement object
                # ------------------------------------------------

                element_data = {
                    "element_id": getattr(
                        element,
                        "element_id",
                        None
                    ),

                    "type": getattr(
                        element,
                        "type",
                        None
                    ),

                    "text": getattr(
                        element,
                        "text",
                        None
                    ),

                    "content_description": getattr(
                        element,
                        "content_description",
                        None
                    ),

                    "resource_id": getattr(
                        element,
                        "resource_id",
                        None
                    ),

                    "clickable": getattr(
                        element,
                        "clickable",
                        False
                    ),

                    "enabled": getattr(
                        element,
                        "enabled",
                        True
                    ),

                    "scrollable": getattr(
                        element,
                        "scrollable",
                        False
                    ),

                    "focusable": getattr(
                        element,
                        "focusable",
                        False
                    ),

                    "focused": getattr(
                        element,
                        "focused",
                        False
                    ),

                    "checked": getattr(
                        element,
                        "checked",
                        False
                    ),

                    "selected": getattr(
                        element,
                        "selected",
                        False
                    ),

                    "bounds": getattr(
                        element,
                        "bounds",
                        None
                    ),
                }

            # ====================================================
            # NORMALIZE BOUNDS
            # ====================================================

            bounds = element_data.get("bounds")

            if bounds is not None and not isinstance(
                bounds,
                dict
            ):

                element_data["bounds"] = {
                    "left": getattr(
                        bounds,
                        "left",
                        0
                    ),

                    "top": getattr(
                        bounds,
                        "top",
                        0
                    ),

                    "right": getattr(
                        bounds,
                        "right",
                        0
                    ),

                    "bottom": getattr(
                        bounds,
                        "bottom",
                        0
                    ),
                }

            normalized_elements.append(element_data)

        normalized["elements"] = normalized_elements

        # ========================================================
        # REMOVE NON-SERIALIZABLE VALUES
        # ========================================================

        # timestamp can sometimes be a datetime object.
        # Convert it to a string if necessary.

        timestamp = normalized.get("timestamp")

        if timestamp is not None and not isinstance(
            timestamp,
            str
        ):
            normalized["timestamp"] = str(timestamp)

        return normalized

    # ============================================================
    # PROCESS OBSERVATION
    # ============================================================

    def process_observation(self, observation) -> dict:
        """
        Send an Android observation to the AI Brain,
        get a validated action, and execute it.
        """

        # ========================================================
        # 1. NORMALIZE REAL ANDROID OBSERVATION
        # ========================================================

        normalized_observation = self._normalize_observation(
            observation
        )

        print("\n" + "=" * 60)
        print("ANDROID → AI")
        print("=" * 60)

        print(
            "Screen:",
            normalized_observation.get("screen_id")
        )

        print(
            "Elements:",
            len(
                normalized_observation.get(
                    "elements",
                    []
                )
            )
        )

        # ========================================================
        # 2. AI DECIDES THE NEXT ACTION
        # ========================================================

        print("\nRunning AI Brain...")

        decision = self.ai_brain.decide(
            normalized_observation
        )

        action = decision.get(
            "validated_action"
        )

        if not action:
            raise RuntimeError(
                "AI Brain did not return a validated action."
            )

        print("\nAI ACTION:")
        print(
            "Type:",
            action.get("action_type")
        )

        print(
            "Element:",
            action.get("element_id")
        )

        # ========================================================
        # 3. PREPARE ACTION FOR ANDROID
        # ========================================================

        execution_action = dict(action)

        # --------------------------------------------------------
        # Typing requires text.
        # The shared Action schema does NOT contain text,
        # so we add it only for Android execution.
        # --------------------------------------------------------

        if action.get("action_type") == "type":

            text = self._get_text_for_action(
                action,
                normalized_observation
            )

            if text is not None:
                execution_action["text"] = text

                print(
                    "Text:",
                    text
                )

        # ========================================================
        # 4. EXECUTE ACTION ON ANDROID
        # ========================================================

        print("\nExecuting action on Android...")

        execution_result = self.executor.execute(
            execution_action
        )

        # ========================================================
        # 5. RETURN COMBINED RESULT
        # ========================================================

        return {
            "observation": normalized_observation,
            "decision": decision,
            "action": action,
            "execution_result": execution_result,
        }

    # ============================================================
    # TEST DATA FOR TYPING
    # ============================================================

    def _get_text_for_action(
        self,
        action: dict,
        observation: dict,
    ) -> str | None:
        """
        Get temporary test input for a typing action.

        Later this can be connected to the hackathon
        test-data configuration.
        """

        element_id = action.get(
            "element_id"
        )

        for element in observation.get(
            "elements",
            []
        ):

            if element.get(
                "element_id"
            ) != element_id:
                continue

            content_description = (
                element.get(
                    "content_description"
                )
                or ""
            ).lower()

            resource_id = (
                element.get(
                    "resource_id"
                )
                or ""
            ).lower()

            text = (
                element.get(
                    "text"
                )
                or ""
            ).lower()

            combined = (
                content_description
                + " "
                + resource_id
                + " "
                + text
            )

            # ----------------------------------------------------
            # Password
            # ----------------------------------------------------

            if "password" in combined:
                return "TestPassword123!"

            # ----------------------------------------------------
            # Email
            # ----------------------------------------------------

            if "email" in combined:
                return "test@example.com"

            # ----------------------------------------------------
            # Username
            # ----------------------------------------------------

            if "username" in combined:
                return "testuser"

            # ----------------------------------------------------
            # Generic input
            # ----------------------------------------------------

            return "test"

        return None


# ================================================================
# BASIC TEST
# ================================================================

if __name__ == "__main__":

    print("=" * 60)
    print("AI → ANDROID EXECUTION BRIDGE")
    print("=" * 60)

    bridge = AIAndroidBridge()

    print("\nBridge created successfully.")

    print(
        "AI Brain:",
        type(bridge.ai_brain).__name__
    )

    print(
        "Executor:",
        type(bridge.executor).__name__
    )

    print("\nBRIDGE READY")