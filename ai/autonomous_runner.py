import json
import logging
import time
from pathlib import Path
from typing import Optional

from android import AndroidController
from android.observation import ObservationBuilder
from android.actions import ActionExecutor

from ai.ai_brain import AIBrain
from knowledge.database import init_db, transaction
from knowledge import repositories as repo
from knowledge.screen_manager import ScreenManager
from knowledge.knowledge_pack import generate_and_store

logger = logging.getLogger(__name__)


class AutonomousRunner:
    """
    Autonomous Android App Explorer with Knowledge Engine integration.

    Flow:

        Capture screenshot + UI tree
                    ↓
             Build Observation
                    ↓
        Ingest into Knowledge Engine
                    ↓
                Gemini AI
                    ↓
              Select Action
                    ↓
             Validate Action
                    ↓
             Execute Action
                    ↓
        Record Transition & Next State
                    ↓
                   repeat
    """

    def __init__(
        self,
        max_steps: int = 5,
        mock: bool = False,
        enable_knowledge_engine: bool = True,
        scan_id: Optional[str] = None,
        package_name: Optional[str] = None,
    ):
        self.max_steps = max_steps
        self.mock = mock
        self.enable_knowledge_engine = enable_knowledge_engine
        self.scan_id = scan_id or f"scan_{int(time.time())}"
        self.package_name = package_name or "com.example.app"

        self.executor = ActionExecutor(mock=self.mock)
        self.controller = self.executor.controller
        self.observation_builder = self.executor.builder
        self.ai_brain = AIBrain()

        self.step_count = 0

        # Keep track of actions so we can detect obvious repetition.
        self.action_history = []

        if self.enable_knowledge_engine:
            init_db()
            self.screen_manager = ScreenManager(self.scan_id)

    # ---------------------------------------------------------
    # CAPTURE CURRENT ANDROID SCREEN
    # ---------------------------------------------------------

    def capture_screen(self):
        self.step_count += 1

        screenshot_path = (
            self.executor.config.screenshot_dir /
            f"auto_step_{self.step_count}.png"
        )

        xml_path = (
            self.executor.config.ui_tree_dir /
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

    def run(self) -> dict:

        print("=" * 70)
        print("AUTONOMOUS AI APP EXPLORER (MEMBER 1 + MEMBER 2 + MEMBER 3)")
        print("=" * 70)
        print(f"Scan ID: {self.scan_id}")
        print(f"Package: {self.package_name}")
        print(f"Mock Mode: {self.mock}")
        print(f"Knowledge Engine: {self.enable_knowledge_engine}")
        print(f"Maximum steps: {self.max_steps}")
        print()

        # 1. Scan Creation in Knowledge Base
        if self.enable_knowledge_engine:
            with transaction() as conn:
                repo.ensure_scan(conn, scan_id=self.scan_id, package_name=self.package_name)

        # 2. App Launch & Initial Observation Ingestion
        if self.mock:
            launch_res = self.executor.launch(self.package_name)
            if launch_res.success and launch_res.observation:
                current_obs = launch_res.observation.to_dict()
            else:
                screenshot_path, xml_path = self.capture_screen()
                current_obs = self.build_observation(screenshot_path, xml_path)
        else:
            screenshot_path, xml_path = self.capture_screen()
            current_obs = self.build_observation(screenshot_path, xml_path)

        current_screen_id = None
        if self.enable_knowledge_engine:
            with transaction() as conn:
                screen_dict, created, warnings = self.screen_manager.process_observation(conn, current_obs)
                current_screen_id = screen_dict["screen_id"]
                print(f"[KNOWLEDGE] Initial screen registered: {current_screen_id} (created={created})")

        print("\n[INITIAL OBSERVATION]")
        print("Screen ID:", current_obs.get("screen_id"))
        print("Elements:", len(current_obs.get("elements", [])))

        # 3. Exploration Loop
        for iteration in range(self.max_steps):

            print("\n" + "=" * 70)
            print(f"AUTONOMOUS ITERATION {iteration + 1} / {self.max_steps}")
            print("=" * 70)

            # a. Ask AI what to do
            print("\n[AI] Deciding next action...")
            try:
                decision = self.ai_brain.decide(current_obs)
            except Exception as error:
                print(f"\n[AI ERROR] {error}")
                print("Stopping autonomous exploration.")
                break

            action = decision.get("validated_action")
            if not action:
                print("\nNo valid action returned. Exploration finished.")
                break

            print("\n[AI DECISION]")
            print(json.dumps(action, indent=2))

            # b. Prevent repeated action on same screen
            action_key = (current_screen_id, action.get("action_type"), action.get("element_id"))
            if action_key in self.action_history:
                print("\n[STOP] Action already executed on this screen. Stopping to prevent loop.")
                break
            self.action_history.append(action_key)

            # c. Execute action
            exec_result = self.execute_action(action, current_obs)
            action_success = exec_result.success

            action_payload = {
                "action_id": action.get("action_id"),
                "action_type": action.get("action_type"),
                "element_id": action.get("element_id"),
                "bounds": action.get("bounds"),
                "source_screen_id": current_screen_id,
                "success": action_success,
            }

            # d. Handle failed action
            if not action_success:
                print(f"\n[ACTION FAILED] {exec_result.error}")
                if self.enable_knowledge_engine:
                    with transaction() as conn:
                        repo.upsert_action(conn, scan_id=self.scan_id, action=action_payload)
                break

            # e. Capture next observation
            if exec_result.observation:
                next_obs = exec_result.observation.to_dict()
            else:
                screenshot_path, xml_path = self.capture_screen()
                next_obs = self.build_observation(screenshot_path, xml_path)

            # f. Ingest next observation & record transition edge
            if self.enable_knowledge_engine:
                with transaction() as conn:
                    next_screen_dict, created, warnings = self.screen_manager.process_observation(conn, next_obs)
                    next_screen_id = next_screen_dict["screen_id"]

                    action_payload["target_screen_id"] = next_screen_id
                    repo.upsert_action(conn, scan_id=self.scan_id, action=action_payload)

                    transition_id = repo.insert_transition(
                        conn,
                        scan_id=self.scan_id,
                        source_screen_id=current_screen_id,
                        target_screen_id=next_screen_id,
                        action_id=action.get("action_id"),
                        action_type=action.get("action_type"),
                        element_id=action.get("element_id"),
                        success=True,
                    )
                    print(
                        f"[KNOWLEDGE] Transition recorded: {current_screen_id} "
                        f"--[{action.get('action_type')}]--> {next_screen_id} ({transition_id})"
                    )
                    current_screen_id = next_screen_id

            current_obs = next_obs
            time.sleep(0.5)

        print()
        print("=" * 70)
        print("AUTONOMOUS EXPLORATION FINISHED")
        print("=" * 70)
        print("Actions executed:", len(self.action_history))
        print("Screens processed:", self.step_count)

        # 4. Generate Knowledge Pack
        pack = None
        if self.enable_knowledge_engine:
            print("\n[KNOWLEDGE] Compiling Knowledge Pack...")
            with transaction() as conn:
                pack = generate_and_store(
                    conn,
                    scan_id=self.scan_id,
                    package_name=self.package_name,
                    save_to_disk=True,
                    include_elements=True,
                )
            print(f"[KNOWLEDGE] Knowledge Pack compiled: {pack['pack_id']}")
            print(f"  Screens in pack: {len(pack['screens'])}")
            print(f"  Transitions in pack: {len(pack['transitions'])}")
            print(f"  Journeys discovered: {len(pack['journeys'])}")

        return {
            "success": True,
            "scan_id": self.scan_id,
            "actions_executed": len(self.action_history),
            "knowledge_pack": pack,
        }


# ============================================================
# MAIN TEST
# ============================================================

if __name__ == "__main__":

    runner = AutonomousRunner(
        max_steps=5,
        mock=True,
        enable_knowledge_engine=True,
    )

    runner.run()