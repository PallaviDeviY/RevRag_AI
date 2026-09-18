import json
import time
from pathlib import Path

from android import AndroidController
from android.observation import ObservationBuilder
from android.actions import ActionExecutor

from ai.ai_brain import AIBrain


class AutonomousRunner:
    """
    Autonomous Android App Explorer.

    Flow:

        Capture screenshot + UI tree
                    ↓
             Build Observation
                    ↓
                Gemini AI
                    ↓
              Select Action
                    ↓
             Validate Action
                    ↓
             Execute Action
                    ↓
             Capture new screen
                    ↓
                  repeat
    """

    def __init__(self, max_steps: int = 5):
        self.max_steps = max_steps

        self.controller = AndroidController()
        self.observation_builder = ObservationBuilder()
        self.ai_brain = AIBrain()
        self.executor = ActionExecutor()

        self.step_count = 0

        # Keep track of actions so we can detect obvious repetition.
        self.action_history = []

    # ---------------------------------------------------------
    # CAPTURE CURRENT ANDROID SCREEN
    # ---------------------------------------------------------

    def capture_screen(self):
        self.step_count += 1

        screenshot_path = (
            Path("screenshots") /
            f"auto_step_{self.step_count}.png"
        )

        xml_path = (
            Path("screenshots") /
            f"auto_step_{self.step_count}.xml"
        )

        screenshot_path.parent.mkdir(
            parents=True,
            exist_ok=True
        )

        self.controller.capture_screenshot(
            str(screenshot_path)
        )

        self.controller.dump_ui_hierarchy(
            str(xml_path)
        )

        print(
            f"\n[CAPTURE] Step {self.step_count}"
        )

        print(
            f"Screenshot: {screenshot_path}"
        )

        print(
            f"UI tree: {xml_path}"
        )

        return screenshot_path, xml_path

    # ---------------------------------------------------------
    # BUILD OBSERVATION
    # ---------------------------------------------------------

    def build_observation(
        self,
        screenshot_path,
        xml_path
    ):
        observation = self.observation_builder.from_xml_file(
            str(xml_path),
            screenshot_relpath=str(screenshot_path),
            ui_tree_relpath=str(xml_path),
        )

        # Convert Observation object into a normal dictionary.
        observation_dict = json.loads(
            json.dumps(
                vars(observation),
                default=vars
            )
        )

        return observation_dict

    # ---------------------------------------------------------
    # GET TEST TEXT FOR TYPE ACTION
    # ---------------------------------------------------------

    def get_text_for_action(
        self,
        action,
        observation
    ):
        if action.get("action_type") != "type":
            return None

        element_id = action.get("element_id")

        for element in observation.get("elements", []):

            if element.get("element_id") != element_id:
                continue

            content_description = (
                element.get("content_description") or ""
            ).lower()

            resource_id = (
                element.get("resource_id") or ""
            ).lower()

            text = (
                element.get("text") or ""
            ).lower()

            combined = (
                content_description
                + " "
                + resource_id
                + " "
                + text
            )

            if "password" in combined:
                return "TestPassword123!"

            if "email" in combined:
                return "test@example.com"

            if "username" in combined:
                return "testuser"

            return "test"

        return None

    # ---------------------------------------------------------
    # EXECUTE AI ACTION
    # ---------------------------------------------------------

    def execute_action(
        self,
        action,
        observation
    ):
        execution_action = dict(action)

        text = self.get_text_for_action(
            action,
            observation
        )

        if text is not None:
            execution_action["text"] = text

        print(
            "\n[EXECUTE]"
        )

        print(
            json.dumps(
                execution_action,
                indent=2
            )
        )

        result = self.executor.execute(
            execution_action
        )

        print(
            "[EXECUTE] SUCCESS"
        )

        print(result)

        return result

    # ---------------------------------------------------------
    # CHECK FOR REPEATED ACTION
    # ---------------------------------------------------------

    def is_repeated_action(self, action):
        action_key = (
            action.get("action_type"),
            action.get("element_id")
        )

        if action_key in self.action_history:
            return True

        self.action_history.append(action_key)

        return False

    # ---------------------------------------------------------
    # RUN AUTONOMOUS EXPLORATION
    # ---------------------------------------------------------

    def run(self):

        print("=" * 70)
        print("AUTONOMOUS AI APP EXPLORER")
        print("=" * 70)

        print(
            f"Maximum steps: {self.max_steps}"
        )

        print()

        for iteration in range(self.max_steps):

            print("=" * 70)

            print(
                f"AUTONOMOUS ITERATION {iteration + 1}"
            )

            print("=" * 70)

            # ---------------------------------------------
            # 1. Capture current screen
            # ---------------------------------------------

            screenshot_path, xml_path = (
                self.capture_screen()
            )

            # ---------------------------------------------
            # 2. Build observation
            # ---------------------------------------------

            observation = self.build_observation(
                screenshot_path,
                xml_path
            )

            print(
                "\n[OBSERVATION]"
            )

            print(
                "Screen:",
                observation.get("screen_id")
            )

            print(
                "Elements:",
                len(
                    observation.get(
                        "elements",
                        []
                    )
                )
            )

            # ---------------------------------------------
            # 3. Ask AI what to do
            # ---------------------------------------------

            print(
                "\n[AI] Asking Gemini..."
            )

            try:
                decision = self.ai_brain.decide(
                    observation
                )

            except Exception as error:

                print(
                    "\n[AI ERROR]"
                )

                print(error)

                print(
                    "\nStopping autonomous exploration."
                )

                break

            # ---------------------------------------------
            # 4. Get validated action
            # ---------------------------------------------

            action = decision.get(
                "validated_action"
            )

            print(
                "\n[AI DECISION]"
            )

            print(
                json.dumps(
                    action,
                    indent=2
                )
            )

            if not action:

                print(
                    "\nNo valid action returned."
                )

                print(
                    "Exploration finished."
                )

                break

            # ---------------------------------------------
            # 5. Prevent obvious repeated actions
            # ---------------------------------------------

            if self.is_repeated_action(action):

                print(
                    "\n[STOP] AI selected an action "
                    "that was already executed."
                )

                print(
                    "Exploration finished to prevent a loop."
                )

                break

            # ---------------------------------------------
            # 6. Execute action
            # ---------------------------------------------

            try:

                self.execute_action(
                    action,
                    observation
                )

            except Exception as error:

                print(
                    "\n[EXECUTION ERROR]"
                )

                print(error)

                print(
                    "\nExploration stopped."
                )

                break

            # ---------------------------------------------
            # 7. Give Android time to update
            # ---------------------------------------------

            print(
                "\n[WAIT] Waiting for new screen..."
            )

            time.sleep(2)

        print()
        print("=" * 70)
        print("AUTONOMOUS EXPLORATION FINISHED")
        print("=" * 70)

        print(
            "Actions executed:",
            len(self.action_history)
        )

        print(
            "Screens processed:",
            self.step_count
        )


# ============================================================
# MAIN TEST
# ============================================================

if __name__ == "__main__":

    runner = AutonomousRunner(
        max_steps=5
    )

    runner.run()