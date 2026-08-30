"""TechJam Conversational Search — Shopping Copilot Agent.

Architecture
------------
1. Intent routing        : opening-message template decides Buying / Browsing /
                           Intent Override; a "no preference" reply reveals
                           the Boundary scenario.
2. Dynamic state machine : accumulates disclosed slots (exact constraint
                           phrases, material, color, budget, category) and
                           erases superseded slots on intent override.
3. Multi-route retrieval  : exact-phrase conjunction (dominant) + hard category
                           intersection + synthetic attribute filters + title /
                           profile-tag / popularity scoring, with cascade
                           relaxation.
4. Proactive guidance     : attribute-sequenced clarification. "feature" is
                           asked first because the simulator discloses
                           constraints in card order and feature-class strings
                           are the selective exact phrases; "other" mops up
                           the remaining slots.

All retrieval runs in-memory with the Python standard library; no LLM call is
required for the deterministic core (reported usage is 0 tokens).
"""
from __future__ import annotations

from pathlib import Path

from src.extract import parse
from src.index import CatalogIndex
from src.llm_rank import LLMReranker
from src.retrieve import retrieve
from src.state import ConversationState, PLANS
from src.tree import ProductTree

try:
    from src.dense import DenseIndex
except ImportError:  # scikit-learn optional; deterministic core still runs
    DenseIndex = None  # type: ignore[assignment]

# Default candidate count exposed for importers; respond() takes top_k per turn instead.
TOP_K = 10

# Slot -> question text. "feature" leads because disclosed constraints arrive in card
# order and feature-class strings are the selective exact phrases; "other" mops up
# whatever slots remain. See the module docstring for the full ordering rationale.
ASK_MESSAGES = {
    "feature": "What specific feature matters most to you here?",
    "material": "Do you have a material preference?",
    "color": "Any color preference?",
    "size": "What size do you need?",
    "style": "Any style or fit preference?",
    "brand": "Do you have a brand in mind?",
    "budget": "What budget range are you thinking of?",
    "use_case": "What will you use it for?",
    "other": "Anything else you'd like to narrow down — material, color, budget, or a particular feature?",
}
# Sent when the state machine has no further question to ask (next_ask returns None).
FINAL_MESSAGE = "Here are the best matches for you."


class Agent:
    """Stateful in-memory shopping copilot that turns user turns into ranked products.

    This is the public entry point the TechJam evaluator imports and drives. It keeps
    one :class:`ConversationState` per session, runs deterministic parsing and
    multi-route retrieval every turn, and replies with a clarification question plus a
    best-first list of ``parent_asin`` recommendations. The core path needs no network
    and no LLM; the optional dense index and LLM reranker degrade gracefully to None.
    """

    def __init__(self, catalog_path: str | Path = "data/catalog.jsonl") -> None:
        """Build the in-memory catalog index and wire up every retrieval route.

        Loads products into a :class:`CatalogIndex`, optionally constructs a
        :class:`DenseIndex` for the dense route, creates the LLM reranker from
        environment config, initialises the per-session state table, and builds the
        :class:`ProductTree` used for attribute-sequenced clarification.

        Side effects: reads the catalog file at ``catalog_path`` and allocates the
        in-memory index. Any dense-index construction failure (missing dependency or
        runtime error) is swallowed so the sparse deterministic core keeps working.
        """
        self.catalog_path = Path(catalog_path)
        self.index = CatalogIndex(self.catalog_path)
        try:
            # Optional dense route; a construction failure falls back to sparse-only retrieval.
            self.dense = DenseIndex(self.index.products) if DenseIndex is not None else None
        except Exception:
            self.dense = None
        self.llm = LLMReranker.from_env()
        # One ConversationState per session_id, created lazily by reset().
        self._sessions: dict[str, ConversationState] = {}
        self.tree = ProductTree(self.index)

    # ------------------------------------------------------------------ API
    def reset(self, session_id: str, user_profile: dict) -> None:
        """Start (or restart) the conversation for a session.

        Creates and stores a fresh :class:`ConversationState` keyed by ``session_id``,
        seeding it with the caller-supplied profile. A falsy profile is normalised to
        ``{}`` so downstream profile lookups never observe None.

        Returns None; the side effect is overwriting any prior state for this session.
        """
        self._sessions[session_id] = ConversationState(
            session_id=session_id, user_profile=user_profile or {}
        )

    def respond(self, session_id: str, user_message: str, turn: int, top_k: int) -> dict:
        """Handle one conversational turn and produce the agent's reply.

        Appends the raw message to history, parses it into disclosed constraints,
        applies those constraints to the session state, runs multi-route retrieval, and
        returns the next clarification question together with ranked recommendations.

        Contract: the returned dict matches the evaluator's shape — ``message``,
        optional ``ask_attribute``, a best-first list of ``{"parent_asin": ...}``
        objects, and token ``usage``. ``turn == 1`` is the only opening turn: it fixes
        intent, records exact phrases, and initialises the question plan; later turns
        only apply new constraints (and erase superseded slots) without resetting intent.

        Side effects: mutates the stored :class:`ConversationState` (history, slots,
        plan, and last pool size). Assumes ``reset()`` has been called for this session.
        """
        state = self._sessions[session_id]
        state.history.append(user_message)
        parsed = parse(user_message, self.index)
        if turn == 1:
            # Opening turn: fix intent and record the exact phrases before applying.
            state.opening_phrases = set(parsed.phrases)
            state.apply(parsed, is_opening=True)
            # Seed the question plan for the routed intent (buying / browsing / override).
            state.plan = list(PLANS[state.intent])
        else:
            # Later turns: apply new constraints; superseded slots are erased inside apply().
            state.apply(parsed)

        ranked, usage, pool_size = retrieve(state, self.index, top_k, dense=self.dense,
                                            llm=self.llm, tree=self.tree)
        state.last_pool_size = pool_size
        # Shape the ASIN ranking into the evaluator's recommendation objects.
        recommendations = [{"parent_asin": asin} for asin in ranked]

        ask_attribute = state.next_ask()
        # Map the next clarification slot to a prompt, or send the final message when done.
        message = ASK_MESSAGES.get(ask_attribute, FINAL_MESSAGE) if ask_attribute else FINAL_MESSAGE

        return {
            "message": message,
            "ask_attribute": ask_attribute,
            "recommendations": recommendations,
            "usage": usage,
        }
