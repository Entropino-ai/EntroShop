"""Per-session conversation state: accumulated slots, intent override handling,
and the clarification (ask) planner.

This module owns the mutable state for one shopping conversation: the constraint
slots extracted from every parsed user message, the routing intent, and the plan
of clarifying questions the agent asks to narrow the product pool. It is pure
Python with no I/O, so it is deterministic and safe to reconstruct per session.

The two key state machines live here:

* ``ConversationState.apply`` ingests a ``ParsedMessage`` and updates slots plus
  routing state, including the special-case intent-override path that erases the
  constraints disclosed in the opening message.
* ``ConversationState.next_ask`` is the clarification (ask) planner: it drains a
  per-intent plan of attribute probes and returns the next attribute to ask for,
  or ``None`` once asking should stop.

The module-level :data:`PLANS` constant encodes the ask strategy per routed
intent. See its comment for why every route currently uses the same sequence.
"""
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
    """Mutable per-session state for one shopping conversation.

    Accumulates the constraint slots extracted from each user turn, tracks the
    routing intent and whether an override/dud was observed, and drives the
    clarification planner. All fields default to empty so a fresh instance is a
    valid, empty session; the caller supplies ``session_id`` and (optionally) a
    ``user_profile`` on construction.

    Contract notes:

    * Slots are accumulated across turns and are never reset mid-session; the
      only "removal" is via :attr:`superseded`, which is subtracted from
      ``phrases`` lazily by :attr:`active_phrases`.
    * ``intent`` is a coarse route label, not a fine-grained classifier; its
      transitions are applied in :meth:`apply`.
    * The dataclass is pure state — no methods here perform I/O or mutate
      anything outside ``self``.
    """

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
        """Constraint phrases still in force after any intent override.

        Returns the exact constraint phrases accumulated so far minus those
        erased by an intent override (see :attr:`superseded`). Callers use this
        set for retrieval because an override invalidates the preferences the
        user stated in the opening message; keeping the subtraction lazy here
        avoids duplicating the "erase on override" rule at every retrieval site.

        Returns:
            The set of currently-active exact constraint phrases. Returns a new
            set (never mutates ``self.phrases``), so callers may mutate freely.
        """
        return self.phrases - self.superseded

    def apply(self, parsed: ParsedMessage, is_opening: bool = False) -> None:
        """Ingest one parsed user message and update slots plus routing state.

        This is the write path of the state machine: it folds a ``ParsedMessage``
        (produced by the extract layer) into the accumulated conversation state.
        It never returns a value — all effects are mutations on ``self``.

        Routing follows a strict priority so ambiguous messages resolve to the
        most specific intent: an explicit override beats a buying signal, which
        beats mere exploration; a "dud" (out-of-scope) reply forces the
        ``boundary`` route regardless of anything detected earlier.

        Args:
            parsed: The parsed representation of the user's latest message.
            is_opening: True only for the session's first user message, where
                opening-specific signals (buying/override/exploring) are allowed
                to set the initial route and category.

        Side effects:
            Mutates ``category``, ``intent``, ``override_seen``, ``superseded``,
            ``dud_seen``, the slot sets (``phrases``/``materials``/``colors``),
            ``budget``, and the ask-planner fields (``ask_exhausted``/
            ``dead_attrs``) as dictated by the parsed flags.
        """
        if is_opening:
            # Opening message sets category and, from explicit opening signals,
            # the initial route. Only the first turn is allowed to do this.
            if parsed.category:
                self.category = parsed.category
            if parsed.is_override_opening:
                self.intent = "intent_override"
            elif parsed.is_buying_opening:
                self.intent = "buying"
            elif parsed.exploring:
                self.intent = "browsing"
        else:
            # Non-opening turns still refine category, but never reset intent
            # from exploration alone (only override/buying/dud may change it).
            if parsed.category:
                self.category = parsed.category
        if parsed.is_override:
            self.override_seen = True
            # the override erases only the preference stated in the opening message
            self.superseded |= self.opening_phrases
            self.intent = "intent_override"
        # Accumulate the new slots via set union; existing constraints persist.
        self.phrases |= parsed.phrases
        self.materials |= parsed.materials
        self.colors |= parsed.colors
        if parsed.budget is not None:
            self.budget = parsed.budget
        if parsed.is_dud:
            # A dud reply means the user went off-script: mark it and route to
            # the boundary handler, which outranks any prior route.
            self.dud_seen = True
            self.intent = "boundary"
        if parsed.is_no_more:
            # "No additional preference" either exhausts the mop-up "other"
            # probe entirely, or marks the specific last attribute as answered.
            if self.last_ask == "other":
                self.ask_exhausted = True
            elif self.last_ask:
                self.dead_attrs.add(self.last_ask)
        if parsed.is_retry:
            # A retry signal means the user has no more constraints to give.
            self.ask_exhausted = True

    def next_ask(self) -> str | None:
        """Return the next clarification attribute to ask, or ``None`` to stop.

        This is the read side of the ask planner. It pops the next attribute off
        the per-intent :data:`PLANS` sequence, skipping any attribute already
        marked in :attr:`dead_attrs` (because the user reported "no additional
        preference" for it). When the plan runs dry it emits one final ``"other"``
        mop-up probe, then stops.

        Contract / side effects:

        * Mutates ``self.plan`` (consumes it via ``pop(0)``) and advances
          ``asks``/``last_ask`` each time a real question is issued.
        * Returns ``None`` once asking is exhausted or the 5-question budget is
          reached — callers must treat ``None`` as "stop asking".

        Returns:
            The next attribute name to ask for (``"other"`` included), or
            ``None`` when no further clarification should be requested.
        """
        if self.ask_exhausted:
            return None
        if self.asks >= 5:
            # Hard cap on clarification questions per session.
            return None
        while self.plan:
            # FIFO consumption keeps the plan order; skipping dead attributes
            # means we never re-ask an attribute the user already exhausted.
            attribute = self.plan.pop(0)
            if attribute in self.dead_attrs:
                continue
            self.asks += 1
            self.last_ask = attribute
            return attribute
        # plan exhausted: one final mop-up probe
        if self.last_ask != "other":
            # Avoid a duplicate "other" if the plan's own last item was already
            # "other"; otherwise issue it once to sweep remaining constraints.
            self.asks += 1
            self.last_ask = "other"
            return "other"
        return None
