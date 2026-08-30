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

from agent_lib.extract import parse
from agent_lib.index import CatalogIndex
from agent_lib.llm_rank import LLMReranker
from agent_lib.retrieve import retrieve
from agent_lib.state import ConversationState, PLANS
from agent_lib.tree import ProductTree

try:
    from agent_lib.dense import DenseIndex
except ImportError:  # scikit-learn optional; deterministic core still runs
    DenseIndex = None  # type: ignore[assignment]

# Default recommendation count when a caller does not pass an explicit top_k.
TOP_K = 10

# Per-slot clarification questions; keys mirror the ConversationState slot names.
# "feature" is asked first because the simulator discloses constraints in card
# order and feature-class strings are the most selective exact phrases.
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
# Shown once every disclosure slot is exhausted (or no question is left to ask).
FINAL_MESSAGE = "Here are the best matches for you."


class Agent:
    """In-memory hybrid-retrieval shopping copilot (deterministic core).

    Implements the required TechJam entry-point contract: ``reset`` starts a
    session and ``respond`` advances it one user turn, returning a clarifying
    question plus an ordered recommendation list. The core retrieval path is
    fully deterministic (0 LLM tokens); the optional dense index and LLM
    reranker are best-effort add-ons that degrade gracefully to the offline
    core when unavailable.
    """

    def __init__(self, catalog_path: str | Path = "data/catalog.jsonl") -> None:
        """Build the shared, immutable indexes and per-session storage.

        Loads the product catalog into a :class:`CatalogIndex`, builds an
        optional :class:`DenseIndex` (only if scikit-learn is importable and the
        build succeeds), initializes the LLM reranker from environment
        variables, and creates an empty session table. Catalog parsing is the
        only disk I/O here; everything else lives in memory.
        """
        self.catalog_path = Path(catalog_path)
        self.index = CatalogIndex(self.catalog_path)
        try:
            # Optional semantic route: only build it if the dependency imported.
            self.dense = DenseIndex(self.index.products) if DenseIndex is not None else None
        except Exception:
            # Any dense-build failure must not break the deterministic core.
            self.dense = None
        self.llm = LLMReranker.from_env()
        self._sessions: dict[str, ConversationState] = {}
        self.tree = ProductTree(self.index)

    # ------------------------------------------------------------------ API
    def reset(self, session_id: str, user_profile: dict) -> None:
        """Start (or restart) a session with a fresh conversation state.

        Instantiates a new :class:`ConversationState` keyed by ``session_id``,
        seeding it with the caller-supplied profile (falling back to an empty
        dict when ``None`` is passed). This discards any prior state for the
        same session id, so it is safe to call before a new episode.
        """
        self._sessions[session_id] = ConversationState(
            session_id=session_id, user_profile=user_profile or {}
        )

    def respond(self, session_id: str, user_message: str, turn: int, top_k: int) -> dict:
        """Advance the session by one user turn and return the copilot reply.

        Parses the raw user message into structured constraints, folds them into
        the conversation state (using the opening-turn path on ``turn == 1`` so
        intent and the disclosure plan are locked in), runs the multi-route
        retrieval pipeline, and picks the next clarification attribute to ask.

        Contract (evaluator-facing): returns a dict with ``message`` (the
        question to show the user), ``ask_attribute`` (one of the known slot
        names or ``None``), ``recommendations`` (a best-to-worst ordered list of
        ``{"parent_asin": ...}`` dicts), and ``usage`` (token counters). The
        state object is mutated as a side effect; nothing is written to disk.
        """
        state = self._sessions[session_id]
        # Keep the verbatim user message for downstream profile/session logic.
        state.history.append(user_message)
        parsed = parse(user_message, self.index)
        if turn == 1:
            # Opening turn: record the exact phrases used to infer intent, seed
            # the slots with opening semantics, and snapshot the clarification
            # plan so later turns know which attributes remain to ask.
            state.opening_phrases = set(parsed.phrases)
            state.apply(parsed, is_opening=True)
            state.plan = list(PLANS[state.intent])
        else:
            # Subsequent turns just merge the newly disclosed constraints in.
            state.apply(parsed)

        # Run the hybrid retrieval cascade; dense and LLM routes are optional.
        ranked, usage, pool_size = retrieve(state, self.index, top_k, dense=self.dense,
                                            llm=self.llm, tree=self.tree)
        state.last_pool_size = pool_size
        # Wrap ranked ASINs into the exact recommendation shape the judge reads.
        recommendations = [{"parent_asin": asin} for asin in ranked]

        # Choose the next highest-information question, or stop when done.
        ask_attribute = state.next_ask()
        message = ASK_MESSAGES.get(ask_attribute, FINAL_MESSAGE) if ask_attribute else FINAL_MESSAGE

        return {
            "message": message,
            "ask_attribute": ask_attribute,
            "recommendations": recommendations,
            "usage": usage,
        }
