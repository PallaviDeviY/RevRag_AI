import json


# ============================================================
# EXPLORATION MEMORY
# ============================================================

class ExplorationMemory:
    """
    Stores what the autonomous agent has observed and done
    during the current exploration session.

    Responsibilities:
        - Remember visited screens
        - Remember executed actions
        - Remember screen transitions
        - Detect repeated actions
        - Detect repeated transitions
        - Detect simple exploration loops
        - Provide compact exploration summary
    """

    def __init__(self):
        # Screens observed
        self.visited_screens = {}

        # Actions performed
        self.action_history = []

        # Screen-to-screen transitions
        self.transitions = []

    # ========================================================
    # RECORD SCREEN
    # ========================================================

    def record_screen(self, observation):
        """Record that a screen has been observed."""

        screen_id = observation.get("screen_id")

        if not screen_id:
            return

        if screen_id not in self.visited_screens:
            self.visited_screens[screen_id] = {
                "screen_id": screen_id,
                "package_name": observation.get("package_name"),
                "activity": observation.get("activity"),
                "observation_ids": [],
                "visit_count": 0,
            }

        screen_info = self.visited_screens[screen_id]

        observation_id = observation.get("observation_id")

        if (
            observation_id
            and observation_id not in screen_info["observation_ids"]
        ):
            screen_info["observation_ids"].append(observation_id)

        screen_info["visit_count"] += 1

    # ========================================================
    # RECORD ACTION
    # ========================================================

    def record_action(self, action, source_screen_id=None):
        """Record an action selected by the AI."""

        if not action:
            return

        action_record = {
            "action_id": action.get("action_id"),
            "action_type": action.get("action_type"),
            "element_id": action.get("element_id"),
            "source_screen_id": source_screen_id,
        }

        self.action_history.append(action_record)

    # ========================================================
    # RECORD TRANSITION
    # ========================================================

    def record_transition(
        self,
        source_screen_id,
        action,
        target_screen_id,
    ):
        """Record a screen-to-screen transition."""

        if not source_screen_id or not target_screen_id:
            return

        transition = {
            "source_screen_id": source_screen_id,
            "action_id": (
                action.get("action_id")
                if action
                else None
            ),
            "action_type": (
                action.get("action_type")
                if action
                else None
            ),
            "element_id": (
                action.get("element_id")
                if action
                else None
            ),
            "target_screen_id": target_screen_id,
        }

        self.transitions.append(transition)

    # ========================================================
    # CHECK SCREEN
    # ========================================================

    def has_seen_screen(self, screen_id):
        """Return True if the screen has already been observed."""

        return screen_id in self.visited_screens

    # ========================================================
    # SCREEN VISIT COUNT
    # ========================================================

    def get_screen_visit_count(self, screen_id):
        """Return how many times a screen has been observed."""

        screen_info = self.visited_screens.get(screen_id)

        if not screen_info:
            return 0

        return screen_info.get("visit_count", 0)

    # ========================================================
    # CHECK TRANSITION
    # ========================================================

    def has_seen_transition(
        self,
        source_screen_id,
        element_id,
        target_screen_id,
    ):
        """
        Check whether the same transition has already happened.
        """

        for transition in self.transitions:
            if (
                transition.get("source_screen_id")
                == source_screen_id
                and
                transition.get("element_id")
                == element_id
                and
                transition.get("target_screen_id")
                == target_screen_id
            ):
                return True

        return False

    # ========================================================
    # CHECK REPEATED ACTION
    # ========================================================

    def has_repeated_action(
        self,
        source_screen_id,
        element_id,
        action_type,
    ):
        """
        Check whether the same action was already performed
        from the same screen.
        """

        for action in self.action_history:
            if (
                action.get("source_screen_id")
                == source_screen_id
                and
                action.get("element_id")
                == element_id
                and
                action.get("action_type")
                == action_type
            ):
                return True

        return False

    # ========================================================
    # DETECT SIMPLE LOOP
    # ========================================================

    def is_looping(self):
        """
        Detect an A -> B -> A -> B style loop.

        Example:

            A -> B
            B -> A
            A -> B
            B -> A

        Returns True when the same two-screen cycle repeats.
        """

        if len(self.transitions) < 4:
            return False

        last_four = self.transitions[-4:]

        first = last_four[0]
        second = last_four[1]
        third = last_four[2]
        fourth = last_four[3]

        pattern_one = (
            first.get("source_screen_id")
            == third.get("source_screen_id")
            and
            first.get("target_screen_id")
            == third.get("target_screen_id")
        )

        pattern_two = (
            second.get("source_screen_id")
            == fourth.get("source_screen_id")
            and
            second.get("target_screen_id")
            == fourth.get("target_screen_id")
        )

        return pattern_one and pattern_two

    # ========================================================
    # DETECT REPEATED SCREEN
    # ========================================================

    def is_screen_repeating(self, screen_id, max_visits=3):
        """
        Detect whether a screen has been visited too many times.

        This prevents the agent from spending unlimited time
        on the same screen.
        """

        return (
            self.get_screen_visit_count(screen_id)
            >= max_visits
        )

    # ========================================================
    # DETECT REPEATED TRANSITION
    # ========================================================

    def is_transition_repeating(
        self,
        source_screen_id,
        element_id,
        target_screen_id,
    ):
        """
        Return True when the same transition has already happened.
        """

        return self.has_seen_transition(
            source_screen_id,
            element_id,
            target_screen_id,
        )

    # ========================================================
    # GLOBAL STOP CONDITION
    # ========================================================

    def should_stop(
        self,
        current_screen_id=None,
        max_steps=20,
        max_screen_visits=3,
    ):
        """
        Decide whether autonomous exploration should stop.

        Stop conditions:

            1. Maximum number of actions reached
            2. Current screen repeated too many times
            3. A simple two-screen loop detected
        """

        # ----------------------------------------------------
        # Maximum exploration steps
        # ----------------------------------------------------

        if len(self.action_history) >= max_steps:
            return True, "MAX_STEPS_REACHED"

        # ----------------------------------------------------
        # Repeated screen
        # ----------------------------------------------------

        if (
            current_screen_id
            and
            self.is_screen_repeating(
                current_screen_id,
                max_screen_visits,
            )
        ):
            return True, "SCREEN_REPEATED"

        # ----------------------------------------------------
        # A -> B -> A -> B loop
        # ----------------------------------------------------

        if self.is_looping():
            return True, "LOOP_DETECTED"

        return False, None

    # ========================================================
    # LOOP REASON
    # ========================================================

    def get_loop_reason(self):
        """Return a human-readable loop explanation."""

        if self.is_looping():
            return (
                "The agent is repeating a "
                "two-screen transition cycle."
            )

        return None

    # ========================================================
    # ACTION HISTORY
    # ========================================================

    def get_action_history(self):
        """Return a copy of the action history."""

        return list(self.action_history)

    # ========================================================
    # TRANSITIONS
    # ========================================================

    def get_transitions(self):
        """Return a copy of recorded transitions."""

        return list(self.transitions)

    # ========================================================
    # SUMMARY
    # ========================================================

    def get_summary(self):
        """
        Return a compact summary of the exploration session.
        """

        return {
            "visited_screen_count": len(
                self.visited_screens
            ),

            "action_count": len(
                self.action_history
            ),

            "transition_count": len(
                self.transitions
            ),

            "visited_screens": list(
                self.visited_screens.values()
            ),

            "transitions": list(
                self.transitions
            ),

            "is_looping": self.is_looping(),

            "loop_reason": self.get_loop_reason(),
        }

    # ========================================================
    # CLEAR MEMORY
    # ========================================================

    def clear(self):
        """Reset the exploration session."""

        self.visited_screens.clear()
        self.action_history.clear()
        self.transitions.clear()


# ============================================================
# TEST
# ============================================================

if __name__ == "__main__":

    memory = ExplorationMemory()

    # --------------------------------------------------------
    # Test observations
    # --------------------------------------------------------

    observation_a = {
        "observation_id": "obs_000001",
        "screen_id": "screen_000001",
        "package_name": "com.example.app",
        "activity": "com.example.app.MainActivity",
    }

    observation_b = {
        "observation_id": "obs_000002",
        "screen_id": "screen_000002",
        "package_name": "com.example.app",
        "activity": "com.example.app.LoginActivity",
    }

    memory.record_screen(observation_a)
    memory.record_screen(observation_b)

    # --------------------------------------------------------
    # Test actions
    # --------------------------------------------------------

    action_a_to_b = {
        "action_id": "action_000001",
        "action_type": "tap",
        "element_id": "element_000004",
    }

    action_b_to_a = {
        "action_id": "action_000002",
        "action_type": "tap",
        "element_id": "element_000005",
    }

    # --------------------------------------------------------
    # Simulate:
    #
    # A -> B
    # B -> A
    # A -> B
    # B -> A
    # --------------------------------------------------------

    memory.record_action(
        action_a_to_b,
        "screen_000001",
    )

    memory.record_transition(
        "screen_000001",
        action_a_to_b,
        "screen_000002",
    )

    memory.record_action(
        action_b_to_a,
        "screen_000002",
    )

    memory.record_transition(
        "screen_000002",
        action_b_to_a,
        "screen_000001",
    )

    memory.record_action(
        action_a_to_b,
        "screen_000001",
    )

    memory.record_transition(
        "screen_000001",
        action_a_to_b,
        "screen_000002",
    )

    memory.record_action(
        action_b_to_a,
        "screen_000002",
    )

    memory.record_transition(
        "screen_000002",
        action_b_to_a,
        "screen_000001",
    )

    # --------------------------------------------------------
    # Test results
    # --------------------------------------------------------

    print("\n" + "=" * 60)
    print("EXPLORATION MEMORY TEST")
    print("=" * 60)

    print(
        "Has seen screen_000001:",
        memory.has_seen_screen(
            "screen_000001"
        ),
    )

    print(
        "Has seen A -> B transition:",
        memory.has_seen_transition(
            "screen_000001",
            "element_000004",
            "screen_000002",
        ),
    )

    print(
        "Has repeated A -> B action:",
        memory.has_repeated_action(
            "screen_000001",
            "element_000004",
            "tap",
        ),
    )

    print(
        "Is looping:",
        memory.is_looping(),
    )

    print(
        "Loop reason:",
        memory.get_loop_reason(),
    )

    # --------------------------------------------------------
    # Test global stop condition
    # --------------------------------------------------------

    should_stop, reason = memory.should_stop(
        current_screen_id="screen_000001",
        max_steps=20,
        max_screen_visits=3,
    )

    print(
        "Should stop:",
        should_stop,
    )

    print(
        "Stop reason:",
        reason,
    )

    # --------------------------------------------------------
    # Summary
    # --------------------------------------------------------

    print("\n" + "=" * 60)
    print("MEMORY SUMMARY")
    print("=" * 60)

    print(
        json.dumps(
            memory.get_summary(),
            indent=2,
            ensure_ascii=False,
        )
    )

    print("\n" + "=" * 60)
    print("EXPLORATION MEMORY TEST COMPLETE")
    print("=" * 60)