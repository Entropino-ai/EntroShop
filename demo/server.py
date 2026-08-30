"""Demo server for the Shopping Copilot agent.

Serves a single-page UI and a small JSON API.

Modes
-----
demo : replay the official deterministic simulator. The server picks a public
       sample (optionally filtered by scenario), drives the simulated customer
       with the evaluator's own policy, and reports ground truth for the hit
       banner. Identical semantics to evaluator.local_evaluator.evaluate().
chat : free-form conversation. The visitor types customer messages; the agent
       parses them with the same message-understanding pipeline.

Run from the repository root:
    python3 demo/server.py --port 8090
"""
from __future__ import annotations

import argparse
import json
import random
import sys
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from agent_lib.extract import parse  # noqa: E402
from agent_lib.guide import (  # noqa: E402
    NEGATIVE_RE,
    STARTER_CATEGORIES,
    GuideState,
    choose_facet,
    guide_message,
    hard_pool,
    option_labels,
)
from agent_lib.llm_rank import LLMReranker  # noqa: E402
from agent_lib.mcp import MCPContext, handle as mcp_handle  # noqa: E402
from agent_lib.query import freeform_query  # noqa: E402
from agent_lib.retrieve import freeform_retrieve_with_pool  # noqa: E402
from agent_lib.tree import ProductTree  # noqa: E402

try:
    from evaluator.local_evaluator import (  # noqa: E402
        MAX_TURNS,
        TOP_K,
        coarse_category,
        customer_reply,
        initial_message,
        load_jsonl,
        materialize_hidden_fields,
    )
    SIMULATOR_AVAILABLE = True
except Exception:
    # standalone chat mode: the organizer kit (which provides the evaluator
    # and the example simulator) is optional; example presets are disabled
    SIMULATOR_AVAILABLE = False
    MAX_TURNS = 10
    TOP_K = 10

    def load_jsonl(path):  # type: ignore[misc]
        import json as _json
        from pathlib import Path as _Path

        return [_json.loads(line) for line in _Path(path).open(encoding="utf-8") if line.strip()]
from starter.agent import Agent  # noqa: E402

CATALOG = ROOT / "data" / "catalog.jsonl"
PUBLIC = ROOT / "data" / "public_set.jsonl"

AGENT: Agent | None = None
PRODUCTS: dict[str, dict] = {}
CATEGORIES: dict[str, list[str]] = {}
SAMPLES: list[dict] = []
SESSIONS: dict[str, dict] = {}


# ---------------------------------------------------------------- session logic
class DemoSession:
    def __init__(self, agent: Agent, sample: dict, products: dict, categories: dict) -> None:
        self.sid = uuid.uuid4().hex
        self.sample = sample
        self.agent = agent
        self.products = products
        self.categories = categories
        self.world: dict[str, dict] = {}  # asin -> {x, y} entity state
        self.target = str(sample["ground_truth"]["parent_asin"])
        self.card, self.behavior = materialize_hidden_fields(sample, products)
        self.effective = {**sample, "intent_card": self.card, "behavior": self.behavior}
        self.disclosed: set[str] = set()
        self.boundary_used = False
        self.override_applied = sample["scenario_type"] != "intent_override"
        self.turn = 0
        self.done = False
        self.hit = False
        self.hit_turn: int | None = None
        self.hit_rank: int | None = None
        self.next_message = initial_message(
            self.effective,
            coarse_category(self.categories.get(self.target, [])),
            self.disclosed,
        )
        self.agent.reset(self.sid, sample["user_profile"])


class ChatSession:
    def __init__(self, agent: Agent) -> None:
        self.sid = uuid.uuid4().hex
        self.agent = agent
        self.turn = 0
        self.guide = GuideState()
        self.messages: list[str] = []
        self.world: dict[str, dict] = {}  # asin -> {x, y} entity state
        self.agent.reset(self.sid, {})


def product_card(asin: str) -> dict:
    product = PRODUCTS.get(asin, {})
    features = product.get("features") or []
    if isinstance(features, dict):
        feature_list = [f"{key}: {item}" for key, item in features.items()][:4]
    else:
        feature_list = [str(item) for item in features][:4]
    return {
        "parent_asin": asin,
        "title": str(product.get("title") or ""),
        "categories": [str(item) for item in (product.get("categories") or [])],
        "features": feature_list,
        "price": product.get("price"),
        "average_rating": product.get("average_rating"),
        "rating_number": product.get("rating_number"),
        "store": str(product.get("store") or ""),
    }


def tree_chain_of(asin: str | None) -> dict | None:
    """The product's unique n-ary-tree chain (property path root → leaf)
    plus how many catalog products share that exact leaf, for the engine
    panel. Returns None when there is no final pick yet."""
    if asin is None or AGENT is None or getattr(AGENT, "tree", None) is None:
        return None
    chain = AGENT.tree.chain(asin)
    siblings = len(AGENT.tree.products_for(chain))
    return {"asin": asin, "chain": chain, "leaf_products": siblings}


def state_view(session_id: str, parsed) -> dict:
    state = AGENT._sessions[session_id]
    return {
        "intent": state.intent,
        "category": state.category,
        "phrases": sorted(state.active_phrases),
        "superseded": sorted(state.superseded),
        "materials": sorted(state.materials),
        "colors": sorted(state.colors),
        "budget": state.budget,
        "asks": state.asks,
        "ask_exhausted": state.ask_exhausted,
        "dud_seen": state.dud_seen,
        "override_seen": state.override_seen,
        "pool_size": state.last_pool_size,
        "parsed_phrases": sorted(parsed.phrases),
        "parsed_materials": sorted(parsed.materials),
        "parsed_colors": sorted(parsed.colors),
        "parsed_is_override": parsed.is_override,
        "parsed_is_dud": parsed.is_dud,
        "parsed_is_no_more": parsed.is_no_more,
    }


def demo_turn(session: DemoSession, body: dict) -> dict:
    user_message = body.get("user_message") or session.next_message
    session.turn += 1
    turn = session.turn
    parsed = parse(user_message, AGENT.index)
    if turn == 1:
        # mirror starter/agent.py's turn-1 handling for the inspector
        pass
    response = AGENT.respond(session.sid, user_message, turn, TOP_K)
    ranked = [item["parent_asin"] for item in response.get("recommendations", [])]
    if session.override_applied and session.target in ranked[:TOP_K]:
        session.hit = True
        session.hit_turn = turn
        session.hit_rank = ranked.index(session.target) + 1
        session.done = True
    elif turn >= MAX_TURNS:
        session.done = True

    if not session.done:
        override = session.effective.get("behavior", {}).get("override") or {}
        if not session.override_applied and turn + 1 == int(override.get("turn", 3)):
            session.override_applied = True
            new_value = str(override.get("new_value", ""))
            if new_value:
                session.disclosed.add(new_value)
            session.next_message = str(override.get("message", "Actually, please ignore my earlier preference."))
        else:
            session.next_message, session.boundary_used = customer_reply(
                session.effective, response.get("ask_attribute"), session.disclosed, session.boundary_used
            )
    else:
        session.next_message = None

    cards = [product_card(asin) for asin in ranked[:TOP_K]]
    target_rank = ranked.index(session.target) + 1 if session.target in ranked[:TOP_K] else None
    return {
        "mode": "demo",
        "turn": turn,
        "max_turns": MAX_TURNS,
        "user_message": user_message,
        "agent_message": response.get("message", ""),
        "ask_attribute": response.get("ask_attribute"),
        "recommendations": cards,
        "target_rank": target_rank,
        "hit": session.hit,
        "hit_turn": session.hit_turn,
        "hit_rank": session.hit_rank,
        "done": session.done,
        "next_user_message": session.next_message,
        "target": {
            "asin": session.target,
            **product_card(session.target),
            "scenario_type": session.sample["scenario_type"],
            "difficulty": session.sample.get("difficulty_bucket"),
        },
        "profile": session.sample["user_profile"],
        "state": state_view(session.sid, parsed),
        "tree_chain": tree_chain_of(session.target),
        "world": build_world(session.world,
                             list(ranked) + ([session.target] if session.target not in ranked else []),
                             session.target if session.hit else None, session.hit),
        "trace": demo_trace(turn, parsed, state_view(session.sid, parsed), session.hit),
        "usage": response.get("usage", {}),
    }


def _converge_reason(guide: GuideState, pool_size: int, clamped: bool) -> str:
    if clamped:
        return "turn clamp (forced from turn 9)"
    if guide.converged:
        return "explicit convergence (that's it)"
    if pool_size <= 5:
        return f"exact matches ≤5 (now {pool_size})"
    if guide.no_progress >= 2:
        return "no new info for 2 turns"
    if guide.guide_rounds >= 4:
        return "guidance rounds exhausted (4 facets)"
    return "no useful facet left, converge"


GOLDEN_ANGLE = 2.399963229728653


def build_world(world_state: dict, alive_ordered: list[str], final_asin: str | None,
                converged: bool) -> dict:
    """MiroFish-style world: alive candidates swirl around the center by
    score rank (rank 1 nearest the eye); eliminated entities stay faded at
    their last position. The world state persists across turns so entities
    keep identity and visibly converge."""
    import math

    alive = alive_ordered[:200]
    alive_set = set(alive)
    for rank, asin in enumerate(alive):
        radius = 0.06 + 0.40 * math.sqrt(rank / max(len(alive) - 1, 1))
        angle = rank * GOLDEN_ANGLE
        world_state[asin] = {
            "x": 0.5 + radius * math.cos(angle),
            "y": 0.5 + radius * math.sin(angle),
            "alive": True,
        }
    for info in world_state.values():
        if info["x"] is not None and info["alive"] and not info.get("_keep"):
            pass
    for asin, info in world_state.items():
        if asin not in alive_set:
            info["alive"] = False
    # cap the graveyard so the world stays readable
    if len(world_state) > 600:
        for asin in [a for a, info in world_state.items() if not info["alive"]][:len(world_state) - 600]:
            del world_state[asin]
    entities = []
    for asin, info in world_state.items():
        product = AGENT.index.products.get(asin, {})
        entities.append({
            "asin": asin,
            "x": round(info["x"], 4),
            "y": round(info["y"], 4),
            "alive": bool(info["alive"]),
            "final": asin == final_asin,
            "title": str(product.get("title") or "")[:44],
            "price": product.get("price"),
            "rating": product.get("average_rating"),
            "rating_number": product.get("rating_number"),
            "store": str(product.get("store") or ""),
        })
    return {"entities": entities, "alive_count": len(alive), "converged": converged}


def chat_trace(turn: int, parsed, guide: GuideState, pool_size: int, converged: bool,
               clamped: bool, ranked: list[str]) -> dict:
    steps = [
        {"name": "Parse message", "kind": "input",
         "detail": (((", ".join(sorted(parsed.phrases))[:36]) or "no template phrase")
                    + (f" mat:{','.join(sorted(parsed.materials))}" if parsed.materials else "")
                    + (f" col:{','.join(sorted(parsed.colors))}" if parsed.colors else ""))},
        {"name": "Intent routing", "kind": "decision", "detail": "freeform guidance"},
        {"name": "Slot accumulation", "kind": "state",
         "detail": f"kw x {len(guide.keywords)} mat x {len(guide.materials)} col x {len(guide.colors)} budget {guide.budget or '—'}"},
        {"name": "Multi-route retrieval", "kind": "funnel",
         "detail": f"50k -> union -> exact {pool_size}"},
        {"name": "Score & rank", "kind": "funnel",
         "detail": (f"top1: {AGENT.index.products[ranked[0]]['title'][:26]}" if ranked else "—")},
        {"name": "Converge decision", "kind": "decision",
         "detail": _converge_reason(guide, pool_size, clamped) if converged else "continue guiding"},
    ]
    if converged and ranked:
        steps.append({"name": "Final pick", "kind": "output", "detail": f"🎯 {ranked[0]}"})
    return {"turn": turn, "steps": steps}


def demo_trace(turn: int, parsed, state: dict, hit: bool) -> dict:
    steps = [
        {"name": "Parse message", "kind": "input",
         "detail": (((", ".join(sorted(parsed.phrases))[:36]) or "no template phrase")
                    + (f" mat:{','.join(sorted(parsed.materials))}" if parsed.materials else "")
                    + (f" col:{','.join(sorted(parsed.colors))}" if parsed.colors else ""))},
        {"name": "Intent routing", "kind": "decision", "detail": str(state.get("intent"))},
        {"name": "Slot accumulation", "kind": "state",
         "detail": f"phrases x {len(state.get('phrases') or [])} mat x {len(state.get('materials') or [])} col x {len(state.get('colors') or [])}"},
        {"name": "Multi-route retrieval", "kind": "funnel", "detail": f"pool {state.get('pool_size', '—')}"},
        {"name": "Converge decision", "kind": "decision",
         "detail": "🎯 target hit" if hit else "ask for more constraints"},
    ]
    if hit:
        steps.append({"name": "Final pick", "kind": "output", "detail": "target entered Top10"})
    return {"turn": turn, "steps": steps}


def chat_turn(session: ChatSession, body: dict) -> dict:
    user_message = str(body.get("user_message") or "").strip()
    session.turn += 1
    session.messages.append(user_message)
    parsed = parse(user_message, AGENT.index)
    query = freeform_query(user_message)
    # still run the agent for state/message bookkeeping, but rank with the
    # free-form pipeline (MiniLM/TF-IDF dense + synthetic slots + category)
    AGENT.respond(session.sid, user_message, session.turn, TOP_K)

    # --- convergent guidance engine ---
    session.guide.apply(query, user_message)
    accumulated = session.guide.to_query()
    chips: list[dict] = []
    facet = None
    usage = {"prompt_tokens": 0, "completion_tokens": 0}

    if session.guide.is_empty:
        # zero-information query: don't guess with a garbage ranking —
        # ask for the item type first (curated starter categories)
        ranked: list[str] = []
        world_alive: list[str] = []
        pool_size = len(AGENT.index.products)
        is_hard = False
        converged = False
        message = "What are you looking for? Pick a category or type it (Chinese or English):"
        chips = [{"type": "category", "label": label, "message": message_text}
                 for label, message_text in STARTER_CATEGORIES]
        if session.guide.no_progress >= 2:
            # user kept ignoring the starter chips: converge to the most
            # popular item instead of looping forever
            from agent_lib.query import FreeformQuery

            ranked, _, union_size = freeform_retrieve_with_pool(
                FreeformQuery(), AGENT.index, AGENT.dense, 20, pool_limit=200,
                tree=getattr(AGENT, "tree", None))
            world_alive = list(ranked)
            pool_size = union_size
            converged = True
            message = ("No new information for 2 turns — settling on the most "
                       "popular item as the single final recommendation.")
            chips = []
        elif session.turn >= 9:
            # 10-turn clamp: no information arrived — settle on the most
            # popular item so the session still ends with one answer
            from agent_lib.query import FreeformQuery

            ranked, _, union_size = freeform_retrieve_with_pool(
                FreeformQuery(), AGENT.index, AGENT.dense, 20, pool_limit=200,
                tree=getattr(AGENT, "tree", None))
            world_alive = list(ranked)
            pool_size = union_size
            converged = True
            message = (f"Turn limit reached (turn {session.turn}) with no usable "
                       "constraints — settling on the most popular item as the "
                       "single final recommendation.")
            chips = []
    else:
        ranked, pool, union_size = freeform_retrieve_with_pool(accumulated, AGENT.index,
                                                               AGENT.dense, 20, pool_limit=200,
                                                               tree=getattr(AGENT, "tree", None))
        world_alive = list(pool)  # score-ordered sample (up to 200 entities)
        # optional LLM rerank of the top-20 (DeepSeek default on this machine):
        # the LLM understands role semantics ("gift FOR dad") better than the
        # lexical/dense hybrid; failures fall back to the heuristic order
        if AGENT.llm is not None and len(ranked) >= 8:
            candidates = []
            for asin in ranked[:15]:
                product = AGENT.index.products[asin]
                features = product.get("features") or []
                if isinstance(features, dict):
                    feature_list = [f"{key}: {item}" for key, item in features.items()][:3]
                else:
                    feature_list = [str(item) for item in features][:3]
                candidates.append({
                    "parent_asin": asin,
                    "title": product.get("title") or "",
                    "categories": [str(item) for item in (product.get("categories") or [])],
                    "features": feature_list,
                })
            try:
                ordered, usage = AGENT.llm.rerank("\n".join(session.messages), candidates)
                setattr(AGENT, "_llm_fails", 0)
            except Exception as exc:
                fails = getattr(AGENT, "_llm_fails", 0) + 1
                setattr(AGENT, "_llm_fails", fails)
                print(f"[server] chat LLM rerank failed ({fails}x): {exc}", flush=True)
                ordered, usage = None, {"prompt_tokens": 0, "completion_tokens": 0}
                if fails >= 2:
                    print("[server] LLM failing repeatedly — disabling (offline fallback)", flush=True)
                    AGENT.llm = None
            if ordered:
                ranked = ordered + [asin for asin in ranked if asin not in ordered]
        ranked = ranked[:TOP_K]
        # rank over the full union pool (recall quality first); the hard
        # intersection size is reported as the "precisely matched" count
        hard_set = hard_pool(AGENT.index, session.guide, tree=getattr(AGENT, "tree", None))
        is_hard = bool(hard_set)
        pool_size = len(hard_set) if hard_set else union_size
        converged = session.guide.should_converge(pool_size, session.turn)
        clamped = session.turn >= 9 and not session.guide.converged \
            and not NEGATIVE_RE.search(user_message)
        if converged:
            if NEGATIVE_RE.search(user_message):
                # user rejected a small/ambiguous pool: offer a fresh direction
                converged = False
                message = "Not these? Try a different direction — pick a category or tell me what you want:"
                chips = [{"type": "category", "label": label, "message": text}
                         for label, text in STARTER_CATEGORIES]
            elif clamped:
                message = (f"Turn limit reached (turn {session.turn}) — picked the single "
                           f"final recommendation from {pool_size} exact matches. "
                           "Type a new need to restart.")
            else:
                message = (f"Converged: {pool_size} exact matches. Final pick below — "
                           "type a new need to restart.")
        else:
            facet, values = choose_facet(AGENT.index, pool, session.guide)
            if facet is None or not values:
                converged = True
                message = (f"Exact matches: {pool_size}. Final pick below — "
                           "type a new need to restart.")
            else:
                session.guide.guide_rounds += 1
                session.guide.facet_keys.add(facet)
                message = guide_message(pool_size, facet, values)
                chips = option_labels(facet, values)
            if not converged:
                chips.append({"type": "converge", "label": "That's it", "message": "that's it"})
    # ---- staged-filter funnel + consensus signals (the 2025 winners' pattern:
    # show the multi-stage narrowing pipeline and which routes voted) ----
    funnel = {"catalog": len(AGENT.index.products), "union": union_size if not session.guide.is_empty else None,
              "hard": pool_size if is_hard else None, "final": 1 if converged and ranked else None}
    final_asin = ranked[0] if converged and ranked else None
    signals: list[str] = []
    if final_asin:
        corpus = AGENT.index.corpus[final_asin].lower()
        matched_kw = [kw for kw in accumulated.keywords if kw.lower() in corpus]
        if matched_kw:
            signals.append(f"keywords x {len(matched_kw)}")
        if accumulated.materials & AGENT.index.material_sets[final_asin]:
            signals.append("material ✓")
        if accumulated.colors & AGENT.index.color_sets[final_asin]:
            signals.append("color ✓")
        if accumulated.budget is not None and AGENT.index.prices[final_asin] is not None:
            signals.append(f"budget ${AGENT.index.prices[final_asin]:g}")
        coarse_key = " ".join(accumulated.text.lower().split())
        if AGENT.index.category_coarse_key.get(final_asin) == coarse_key:
            signals.append("exact category ✓")
        if AGENT.dense is not None:
            try:
                sims = AGENT.dense.query_scores(" ".join([*accumulated.keywords,
                                                          *accumulated.materials,
                                                          *accumulated.colors]), [final_asin])
                if sims and sims[0][1] > 0.05:
                    signals.append(f"semantic {sims[0][1]:.2f}")
            except Exception:
                pass
        if usage.get("completion_tokens"):
            signals.append("LLM rerank ✓")
        rating, _ = AGENT.index.ratings[final_asin]
        if rating is not None:
            signals.append(f"★{rating}")
    return {
        "mode": "chat",
        "turn": session.turn,
        "user_message": user_message,
        "agent_message": message,
        "ask_attribute": None,
        "recommendations": [product_card(asin) for asin in ranked],
        "hit": None,
        "done": session.turn >= MAX_TURNS,
        "target": None,
        "profile": {},
        "query": {
            "keywords": accumulated.keywords,
            "materials": sorted(accumulated.materials),
            "colors": sorted(accumulated.colors),
            "budget": accumulated.budget,
        },
        "guide": {"converged": converged, "facet": facet, "options": chips,
                  "pool_size": pool_size, "hard": is_hard},
        "final": product_card(ranked[0]) if converged and ranked else None,
        "funnel": funnel,
        "tree_chain": tree_chain_of(final_asin),
        "signals": signals,
        "world": build_world(session.world, world_alive, ranked[0] if (converged and ranked) else None,
                             converged),
        "trace": chat_trace(session.turn, parsed, session.guide, pool_size, converged,
                            session.turn >= 9, ranked),
        "state": state_view(session.sid, parsed),
        "usage": usage,
    }


# --------------------------------------------------------------------- HTTP API
class Handler(BaseHTTPRequestHandler):
    server_version = "TechJamDemo/1.0"

    def log_message(self, *args) -> None:  # quiet
        pass

    def _json(self, payload: dict, status: int = 200) -> None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self) -> None:
        if self.path in ("/", "/index.html"):
            html = (Path(__file__).parent / "index.html").read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(html)))
            self.end_headers()
            self.wfile.write(html)
        elif self.path == "/api/health":
            self._json({"ok": True, "products": len(PRODUCTS), "samples": len(SAMPLES),
                        "llm": AGENT.llm is not None,
                        "llm_ok": AGENT.llm is not None,
                        "llm_model": AGENT.llm.model if AGENT.llm else None,
                        "dense": type(AGENT.dense).__name__})
        else:
            self._json({"error": "not found"}, 404)

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length") or 0)
        try:
            body = json.loads(self.rfile.read(length).decode("utf-8")) if length else {}
        except Exception:
            body = {}
        if self.path == "/api/new":
            mode = body.get("mode", "demo")
            if mode == "chat":
                session = ChatSession(AGENT)
                SESSIONS[session.sid] = session
                self._json({"session_id": session.sid, "mode": "chat", "first_user_message": None,
                            "target": None, "scenario_type": None})
                return
            if not SIMULATOR_AVAILABLE:
                self._json({"error": "example mode needs the organizer kit (clone TechJam2026/"
                            "techjam-conversational-search and add it to PYTHONPATH); "
                            "chat mode works standalone"}, 400)
                return
            if not SAMPLES:
                self._json({"error": "data/public_set.jsonl missing — fetch it from the "
                            "participant kit (see README)"}, 400)
                return
            scenario = body.get("scenario")
            candidates = [s for s in SAMPLES if not scenario or scenario == "random"
                          or s["scenario_type"] == scenario]
            sample = random.choice(candidates or SAMPLES)
            session = DemoSession(AGENT, sample, PRODUCTS, CATEGORIES)
            SESSIONS[session.sid] = session
            self._json({
                "session_id": session.sid,
                "mode": "demo",
                "first_user_message": session.next_message,
                "target": {"asin": session.target, **product_card(session.target),
                           "scenario_type": sample["scenario_type"],
                           "difficulty": sample.get("difficulty_bucket")},
                "scenario_type": sample["scenario_type"],
                "profile": sample["user_profile"],
            })
        elif self.path == "/api/llm":
            # runtime LLM configuration from the UI; keys live only in this
            # server process and the caller's browser, never on disk
            if body.get("clear"):
                AGENT.llm = None
                self._json({"ok": True, "configured": False})
                return
            if body.get("use_local_default"):
                AGENT.llm = LLMReranker.from_local_defaults()
                if AGENT.llm is None:
                    self._json({"ok": False, "configured": False,
                                "error": "no local DeepSeek credentials found (~/.dsh/.credentials.yaml or DEEPSEEK_API_KEY)"}, 400)
                elif not validate_llm(AGENT.llm):
                    AGENT.llm = None
                    self._json({"ok": False, "configured": False,
                                "error": "model unreachable — server stays offline"}, 400)
                else:
                    self._json({"ok": True, "configured": True, "model": AGENT.llm.model,
                                "source": "local"})
                return
            api_base = str(body.get("api_base") or "").strip()
            api_key = str(body.get("api_key") or "").strip()
            model = str(body.get("model") or "gpt-4o-mini").strip()
            if not api_base or not api_key:
                self._json({"ok": False, "configured": False, "error": "api_base and api_key must not be empty"}, 400)
                return
            candidate = LLMReranker(api_base, api_key, model)
            if not validate_llm(candidate):
                AGENT.llm = None
                self._json({"ok": False, "configured": False,
                            "error": "model unreachable — server stays offline"}, 400)
                return
            AGENT.llm = candidate
            self._json({"ok": True, "configured": True, "model": model})
        elif self.path == "/mcp":
            # JSON-RPC 2.0 endpoint (same handler as the stdio server)
            ctx = MCPContext(index=AGENT.index, dense=AGENT.dense,
                             tree=getattr(AGENT, "tree", None))
            response = mcp_handle(ctx, body.get("method"), body.get("params") or {}, body.get("id"))
            if response is None:
                self._json({"jsonrpc": "2.0", "id": None, "result": {}})
            else:
                self._json(response)
        elif self.path == "/api/turn":
            session = SESSIONS.get(body.get("session_id"))
            if session is None:
                self._json({"error": "unknown session"}, 404)
                return
            result = demo_turn(session, body) if isinstance(session, DemoSession) else chat_turn(session, body)
            self._json(result)
        else:
            self._json({"error": "not found"}, 404)


def validate_llm(llm) -> bool:
    """Probe the configured model; if unreachable, the server stays offline
    instead of stalling every chat turn."""
    if llm is None:
        return False
    ok = False
    try:
        ok = llm.ping()
    except Exception:
        ok = False
    if not ok:
        print(f"[server] LLM model unreachable ({llm.model}) — falling back to offline mode", flush=True)
    return ok


def build_dense(products: dict):
    """Strongest available dense route: MiniLM transformer, else TF-IDF."""
    try:
        from agent_lib.dense import product_text
        from agent_lib.dense_transformer import TransformerDense

        texts = {asin: product_text(product) for asin, product in products.items()}
        return TransformerDense(products, texts)
    except Exception as exc:
        print(f"[server] MiniLM unavailable ({exc}); falling back to TF-IDF", flush=True)
    from agent_lib.dense import DenseIndex

    return DenseIndex(products)


def main() -> None:
    global AGENT, PRODUCTS, CATEGORIES, SAMPLES
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8090)
    parser.add_argument("--catalog", default=str(CATALOG))
    parser.add_argument("--dataset", default=str(PUBLIC))
    args = parser.parse_args()

    print(f"building index from {args.catalog} ...", flush=True)
    AGENT = Agent(args.catalog)
    AGENT.dense = build_dense(AGENT.index.products)
    if AGENT.llm is None:
        AGENT.llm = LLMReranker.from_local_defaults()
        if AGENT.llm is not None:
            print(f"[server] LLM: local DeepSeek default ({AGENT.llm.model})", flush=True)
    if AGENT.llm is not None and not validate_llm(AGENT.llm):
        AGENT.llm = None
    setattr(AGENT, "_llm_fails", 0)
    setattr(AGENT, "tree", ProductTree(AGENT.index))
    PRODUCTS = AGENT.index.products
    CATEGORIES = {asin: [str(value) for value in (product.get("categories") or [])]
                  for asin, product in PRODUCTS.items()}
    SAMPLES = load_jsonl(args.dataset) if Path(args.dataset).exists() else []
    print(f"ready: {len(PRODUCTS)} products, {len(SAMPLES)} public sessions, "
          f"dense={type(AGENT.dense).__name__}, simulator={'on' if SIMULATOR_AVAILABLE else 'off (chat only)'}",
          flush=True)

    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    print(f"demo UI: http://127.0.0.1:{args.port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
