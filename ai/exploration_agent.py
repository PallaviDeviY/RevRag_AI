import json

from ai.exploration_memory import ExplorationMemory
from ai.llm_client import (
    get_llm_action,
    validate_llm_action,
    load_observation,
)
from ai.decision_schema import Action
from ai.action_detection import detect_candidate_actions
from ai.ai_brain import AIBrain
from ai.android_bridge import AIAndroidBridge


# ============================================================
# EXPLORATION AGENT
# ============================================================

class ExplorationAgent:
    """
    Autonomous Android exploration agent.

    AI-powered flow:

        Observation
            ↓
        AI Brain
            ↓
        Gemini Vision
            ↓
        LLM Action Proposal
            ↓
        Safety Validation
            ↓
        Final Action
            ↓
        Exploration Memory
    """

    def __init__(self):
        self.memory = ExplorationMemory()
        self.action_counter = 0
        self.ai_brain = AIBrain()
        self.android_bridge = AIAndroidBridge()

    # ========================================================
    # AI BRAIN DECISION
    # ========================================================

    def process_with_ai_brain(
        self,
        observation: dict
    ) -> dict:
        """
        Process one observation using the Gemini-powered
        AI Brain.
        """

        result = self.ai_brain.decide(observation)

        return result

    # ========================================================
    # MULTI-SCREEN AI PROCESSING
    # ========================================================

    def process_multiple_observations(
        self,
        observations: list[dict]
    ) -> list[dict]:
        """
        Process multiple screen observations sequentially
        and store the AI decisions in exploration memory.
        """

        results = []

        for observation in observations:

            # ------------------------------------------------
            # Send observation to AI Brain
            # ------------------------------------------------

            result = self.process_with_ai_brain(
                observation
            )

            # ------------------------------------------------
            # Get screen and action information
            # ------------------------------------------------

            screen_id = observation.get("screen_id")
            action = result.get("validated_action")

            # ------------------------------------------------
            # Record screen in memory
            # ------------------------------------------------

            if screen_id:
                self.memory.record_screen(
                    observation
                )

            # ------------------------------------------------
            # Record AI-selected action in memory
            # ------------------------------------------------

            if action and screen_id:
                self.memory.record_action(
                    source_screen_id=screen_id,
                    action=action,
                )

            # ------------------------------------------------
            # Store result
            # ------------------------------------------------

            results.append(result)

        return results

    # ========================================================
    # ACTION ID
    # ========================================================

    def generate_action_id(self) -> str:
        """
        Generate a unique action ID for this agent session.
        """

        self.action_counter += 1

        return f"action_{self.action_counter:06d}"

    # ========================================================
    # PROCESS OBSERVATION
    # ========================================================

    def process_observation(
        self,
        observation: dict
    ) -> dict:
        """
        Process one Android Observation.

        Gemini proposes the action.
        Python validates the decision.
        """

        # ----------------------------------------------------
        # Basic observation validation
        # ----------------------------------------------------

        required_fields = [
            "observation_id",
            "screen_id",
            "elements",
        ]

        for field in required_fields:

            if field not in observation:
                raise ValueError(
                    f"Observation is missing required field: {field}"
                )

        # ----------------------------------------------------
        # Record screen in memory
        # ----------------------------------------------------

        self.memory.record_screen(
            observation
        )

        # ----------------------------------------------------
        # Ask Gemini for next action
        # ----------------------------------------------------

        print("\n")
        print("=" * 60)
        print("GEMINI IS REASONING...")
        print("=" * 60)

        llm_action = get_llm_action(
            observation
        )

        print("\nGemini Action Proposal:")

        print(
            json.dumps(
                llm_action,
                indent=2
            )
        )

        # ----------------------------------------------------
        # Check for repeated action
        # ----------------------------------------------------

        selected_action = self.handle_repeated_action(
            observation=observation,
            llm_action=llm_action,
        )

        print("\nSelected Action:")

        print(
            json.dumps(
                selected_action,
                indent=2
            )
        )

        # ----------------------------------------------------
        # Validate selected action
        # ----------------------------------------------------

        validated_action = validate_llm_action(
            selected_action,
            observation
        )

        # ----------------------------------------------------
        # Generate agent-owned action ID
        # ----------------------------------------------------

        validated_action["action_id"] = (
            self.generate_action_id()
        )

        # ----------------------------------------------------
        # Validate against Pydantic Action schema
        # ----------------------------------------------------

        final_action = Action.model_validate(
            validated_action
        )

        # ----------------------------------------------------
        # Record action in memory
        # ----------------------------------------------------

        self.memory.record_action(
            source_screen_id=observation["screen_id"],
            action=final_action.model_dump()
        )

        # ----------------------------------------------------
        # Return complete agent result
        # ----------------------------------------------------

        result = {
            "status": "success",

            "screen_id": observation["screen_id"],

            "observation_id": observation["observation_id"],

            "llm_proposal": llm_action,

            "selected_action": selected_action,

            "final_action": final_action.model_dump(),

            "memory": self.memory.get_summary(),
        }

        return result

    # ========================================================
    # RUN SIMULATED EXPLORATION
    # ========================================================

    def run_simulated_exploration(
        self,
        observation_paths: list[str],
    ) -> list[dict]:
        """
        Process multiple observations sequentially.

        This simulates the Android controller sending a new
        Observation after every action.
        """

        results = []

        for step_number, observation_path in enumerate(
            observation_paths,
            start=1
        ):

            print("\n")
            print("=" * 60)
            print(f"EXPLORATION STEP {step_number}")
            print("=" * 60)

            # ------------------------------------------------
            # Load next observation
            # ------------------------------------------------

            observation = load_observation(
                observation_path
            )

            print(
                f"Observation: "
                f"{observation['observation_id']}"
            )

            print(
                f"Screen: "
                f"{observation['screen_id']}"
            )

            # ------------------------------------------------
            # Process observation with Gemini
            # ------------------------------------------------

            result = self.process_observation(
                observation
            )

            results.append(result)

            # ------------------------------------------------
            # Display selected action
            # ------------------------------------------------

            print("\nAction selected:")

            print(
                json.dumps(
                    result["final_action"],
                    indent=2
                )
            )

            # ------------------------------------------------
            # Check for loops
            # ------------------------------------------------

            if self.is_looping():

                print(
                    "\n⚠️ Exploration loop detected."
                )

                break

        return results

    # ========================================================
    # HANDLE REPEATED ACTION
    # ========================================================

    def handle_repeated_action(
        self,
        observation: dict,
        llm_action: dict,
    ) -> dict:
        """
        Check whether Gemini selected an action that has
        already been attempted on the current screen.

        If it has not been attempted, return it unchanged.

        If it has been attempted, search for another
        candidate action on the same screen.
        """

        screen_id = observation["screen_id"]

        element_id = llm_action["element_id"]

        action_type = llm_action["action_type"]

        # ----------------------------------------------------
        # Check memory
        # ----------------------------------------------------

        already_used = self.memory.has_repeated_action(
            source_screen_id=screen_id,
            element_id=element_id,
            action_type=action_type,
        )

        if not already_used:
            return llm_action

        print(
            "\n⚠️ Gemini selected a repeated action."
        )

        print(
            f"Already attempted: "
            f"{element_id} → {action_type}"
        )

        # ----------------------------------------------------
        # Find other available actions
        # ----------------------------------------------------

        candidates = detect_candidate_actions(
            observation
        )

        for candidate in candidates:

            candidate_element_id = candidate.get(
                "element_id"
            )

            candidate_action_type = candidate.get(
                "action_type"
            )

            # ------------------------------------------------
            # Skip the repeated action
            # ------------------------------------------------

            if (
                candidate_element_id == element_id
                and candidate_action_type == action_type
            ):
                continue

            # ------------------------------------------------
            # Check whether candidate was already used
            # ------------------------------------------------

            candidate_repeated = (
                self.memory.has_repeated_action(
                    source_screen_id=screen_id,
                    element_id=candidate_element_id,
                    action_type=candidate_action_type,
                )
            )

            if candidate_repeated:
                continue

            # ------------------------------------------------
            # Found a new action
            # ------------------------------------------------

            print(
                "Using alternative action:"
            )

            print(
                f"{candidate_element_id} "
                f"→ {candidate_action_type}"
            )

            return {
                "element_id": candidate_element_id,
                "action_type": candidate_action_type,
            }

        # ----------------------------------------------------
        # No unused action remains
        # ----------------------------------------------------

        raise RuntimeError(
            f"No unexplored actions remain on screen "
            f"{screen_id}."
        )

    # ========================================================
    # RECORD TRANSITION
    # ========================================================

    def record_transition(
        self,
        source_screen_id: str,
        element_id: str,
        target_screen_id: str,
    ):
        """
        Record that an action caused a transition
        from one screen to another.
        """

        self.memory.record_transition(
            source_screen_id=source_screen_id,
            element_id=element_id,
            target_screen_id=target_screen_id,
        )

    # ========================================================
    # LOOP DETECTION
    # ========================================================

    def is_looping(self) -> bool:
        """
        Check whether the exploration agent appears
        to be stuck in a loop.
        """

        return self.memory.is_looping()

    # ========================================================
    # MEMORY SUMMARY
    # ========================================================

    def get_memory_summary(self) -> dict:
        """
        Return current exploration memory.
        """

        return self.memory.get_summary()

    # ========================================================
    # RESET
    # ========================================================

    def reset(self):
        """
        Reset the exploration session.
        """

        self.memory.clear()
        self.action_counter = 0


# ============================================================
# TEST
# ============================================================

if __name__ == "__main__":

    print("\n")
    print("=" * 60)
    print("AI APP EXPLORER - MULTI-SCREEN TEST")
    print("=" * 60)

    # --------------------------------------------------------
    # Create agent
    # --------------------------------------------------------

    agent = ExplorationAgent()

    # --------------------------------------------------------
    # Simulated observations
    # --------------------------------------------------------

    observation_paths = [
        "data/sample/sample_observation.json",
        "data/sample/sample_observation_2.json",
        "data/sample/sample_observation_3.json",
    ]

    # --------------------------------------------------------
    # Run exploration
    # --------------------------------------------------------

    results = agent.run_simulated_exploration(
        observation_paths
    )

    # --------------------------------------------------------
    # Final summary
    # --------------------------------------------------------

    print("\n")
    print("=" * 60)
    print("EXPLORATION COMPLETE")
    print("=" * 60)

    print(
        f"Observations processed: {len(results)}"
    )

    print(
        f"Actions generated: "
        f"{agent.action_counter}"
    )

    print(
        f"Loop detected: "
        f"{agent.is_looping()}"
    )

    print("\nMemory Summary:")

    print(
        json.dumps(
            agent.get_memory_summary(),
            indent=2
        )
    )