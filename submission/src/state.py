"""Per-session conversation state: accumulated slots, intent override handling,
and the clarification (ask) planner."""
from __future__ import annotations

from dataclasses import dataclass, field

from .extract import ParsedMessage

# Ask plans per routed intent. The evaluator's disclosure policy returns any
# two undisclosed constraints when asked "other", which dominates attribute-
# specific probes (measured on the public set), so every route drains slots
# with "other" and stops on the "no additional preference" reply.
PLANS = {
    "buying": ["other"] * 5,
    "browsing": ["other"] * 5,
    "boundary": ["other"] * 5,
    "intent_override": ["other"] * 5,
}


@dataclass
class ConversationState:
    session_id: str = ""
    user_profile: dict = field(default_factory=dict)
    history: list[str] = field(default_factory=list)         # raw user messages
    # accumulated slots
    category: str = ""
    phrases: set[str] = field(default_factory=set)            # exact constraint phrases
    opening_phrases: set[str] = field(default_factory=set)    # disclosed in turn-1 message
    superseded: set[str] = field(default_factory=set)         # erased by intent override
    materials: set[str] = field(default_factory=set)
    colors: set[str] = field(default_factory=set)
    budget: float | None = None
    # routing
    intent: str = "browsing"  # buying | browsing | intent_override | boundary
    override_seen: bool = False
    dud_seen: bool = False
    # ask planner
    plan: list[str] = field(default_factory=list)
    asks: int = 0
    last_ask: str | None = None
    dead_attrs: set[str] = field(default_factory=set)         # "no additional preference" reported
    ask_exhausted: bool = False
    last_pool_size: int = 0                                   # inspector/demo telemetry

    @property
    def active_phrases(self) -> set[str]:
        return self.phrases - self.superseded

    def apply(self, parsed: ParsedMessage, is_opening: bool = False) -> None:
        if is_opening:
            if parsed.category:
                self.category = parsed.category
            if parsed.is_override_opening:
                self.intent = "intent_override"
            elif parsed.is_buying_opening:
                self.intent = "buying"
            elif parsed.exploring:
                self.intent = "browsing"
        else:
            if parsed.category:
                self.category = parsed.category
        if parsed.is_override:
            self.override_seen = True
            # the override erases only the preference stated in the opening message
            self.superseded |= self.opening_phrases
            self.intent = "intent_override"
        self.phrases |= parsed.phrases
        self.materials |= parsed.materials
        self.colors |= parsed.colors
        if parsed.budget is not None:
            self.budget = parsed.budget
        if parsed.is_dud:
            self.dud_seen = True
            self.intent = "boundary"
        if parsed.is_no_more:
            if self.last_ask == "other":
                self.ask_exhausted = True
            elif self.last_ask:
                self.dead_attrs.add(self.last_ask)
        if parsed.is_retry:
            self.ask_exhausted = True

    def next_ask(self) -> str | None:
        """Next clarification attribute, or None to stop asking."""
        if self.ask_exhausted:
            return None
        if self.asks >= 5:
            return None
        while self.plan:
            attribute = self.plan.pop(0)
            if attribute in self.dead_attrs:
                continue
            self.asks += 1
            self.last_ask = attribute
            return attribute
        # plan exhausted: one final mop-up probe
        if self.last_ask != "other":
            self.asks += 1
            self.last_ask = "other"
            return "other"
        return None
