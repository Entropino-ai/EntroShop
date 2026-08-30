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

TOP_K = 10

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
FINAL_MESSAGE = "Here are the best matches for you."


class Agent:
    """In-memory hybrid-retrieval shopping copilot (deterministic core)."""

    def __init__(self, catalog_path: str | Path = "data/catalog.jsonl") -> None:
        self.catalog_path = Path(catalog_path)
        self.index = CatalogIndex(self.catalog_path)
        try:
            self.dense = DenseIndex(self.index.products) if DenseIndex is not None else None
        except Exception:
            self.dense = None
        self.llm = LLMReranker.from_env()
        self._sessions: dict[str, ConversationState] = {}
        self.tree = ProductTree(self.index)

    # ------------------------------------------------------------------ API
    def reset(self, session_id: str, user_profile: dict) -> None:
        self._sessions[session_id] = ConversationState(
            session_id=session_id, user_profile=user_profile or {}
        )

    def respond(self, session_id: str, user_message: str, turn: int, top_k: int) -> dict:
        state = self._sessions[session_id]
        state.history.append(user_message)
        parsed = parse(user_message, self.index)
        if turn == 1:
            state.opening_phrases = set(parsed.phrases)
            state.apply(parsed, is_opening=True)
            state.plan = list(PLANS[state.intent])
        else:
            state.apply(parsed)

        ranked, usage, pool_size = retrieve(state, self.index, top_k, dense=self.dense,
                                            llm=self.llm, tree=self.tree)
        state.last_pool_size = pool_size
        recommendations = [{"parent_asin": asin} for asin in ranked]

        ask_attribute = state.next_ask()
        message = ASK_MESSAGES.get(ask_attribute, FINAL_MESSAGE) if ask_attribute else FINAL_MESSAGE

        return {
            "message": message,
            "ask_attribute": ask_attribute,
            "recommendations": recommendations,
            "usage": usage,
        }
