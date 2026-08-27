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
from evaluator.local_evaluator import (  # noqa: E402
    MAX_TURNS,
    TOP_K,
    catalog_index,
    coarse_category,
    customer_reply,
    initial_message,
    load_jsonl,
    materialize_hidden_fields,
)
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
        "world": build_world(session.world,
                             list(ranked) + ([session.target] if session.target not in ranked else []),
                             session.target if session.hit else None, session.hit),
        "trace": demo_trace(turn, parsed, state_view(session.sid, parsed), session.hit),
        "usage": response.get("usage", {}),
    }


def _converge_reason(guide: GuideState, pool_size: int, clamped: bool) -> str:
    if clamped:
        return "輪次鉗制（第 9 輪起強制）"
    if guide.converged:
        return "用戶顯式收斂（就這些吧）"
    if pool_size <= 5:
        return f"精確符合 ≤5（現 {pool_size}）"
    if guide.no_progress >= 2:
        return "連續 2 輪無新信息"
    if guide.guide_rounds >= 4:
        return "引導輪次耗盡（4 輪 facet）"
    return "無可用 facet，直接收斂"


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
    entities = [
        {
            "asin": asin,
            "x": round(info["x"], 4),
            "y": round(info["y"], 4),
            "alive": bool(info["alive"]),
            "final": asin == final_asin,
            "title": str(AGENT.index.products.get(asin, {}).get("title") or "")[:44],
        }
        for asin, info in world_state.items()
    ]
    return {"entities": entities, "alive_count": len(alive), "converged": converged}


def chat_trace(turn: int, parsed, guide: GuideState, pool_size: int, converged: bool,
               clamped: bool, ranked: list[str]) -> dict:
    steps = [
        {"name": "消息解析", "kind": "input",
         "detail": ((("、".join(sorted(parsed.phrases))[:36]) or "無模板短語")
                    + (f" 料:{','.join(sorted(parsed.materials))}" if parsed.materials else "")
                    + (f" 色:{','.join(sorted(parsed.colors))}" if parsed.colors else ""))},
        {"name": "意圖路由", "kind": "decision", "detail": "自由對話 · freeform 引導"},
        {"name": "槽位累積", "kind": "state",
         "detail": f"kw×{len(guide.keywords)} 料×{len(guide.materials)} 色×{len(guide.colors)} 預算{guide.budget or '—'}"},
        {"name": "多路檢索", "kind": "funnel",
         "detail": f"50k → 並集 → 精確 {pool_size}"},
        {"name": "打分排序", "kind": "funnel",
         "detail": (f"top1: {AGENT.index.products[ranked[0]]['title'][:26]}" if ranked else "—")},
        {"name": "收斂決策", "kind": "decision",
         "detail": _converge_reason(guide, pool_size, clamped) if converged else "繼續引導（提問/chips）"},
    ]
    if converged and ranked:
        steps.append({"name": "最終推薦", "kind": "output", "detail": f"🎯 {ranked[0]}"})
    return {"turn": turn, "steps": steps}


def demo_trace(turn: int, parsed, state: dict, hit: bool) -> dict:
    steps = [
        {"name": "消息解析", "kind": "input",
         "detail": ((("、".join(sorted(parsed.phrases))[:36]) or "無模板短語")
                    + (f" 料:{','.join(sorted(parsed.materials))}" if parsed.materials else "")
                    + (f" 色:{','.join(sorted(parsed.colors))}" if parsed.colors else ""))},
        {"name": "意圖路由", "kind": "decision", "detail": str(state.get("intent"))},
        {"name": "槽位累積", "kind": "state",
         "detail": f"短語×{len(state.get('phrases') or [])} 料×{len(state.get('materials') or [])} 色×{len(state.get('colors') or [])}"},
        {"name": "多路檢索", "kind": "funnel", "detail": f"檢索池 {state.get('pool_size', '—')}"},
        {"name": "收斂決策", "kind": "decision",
         "detail": "🎯 命中目標" if hit else "提問採集更多約束"},
    ]
    if hit:
        steps.append({"name": "最終推薦", "kind": "output", "detail": "目標商品進入 Top10"})
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
        message = "先告訴我你想找哪類商品？點一個，或直接輸入（中英文都可以）："
        chips = [{"type": "category", "label": label, "message": message_text}
                 for label, message_text in STARTER_CATEGORIES]
        if session.turn >= 9:
            # 10-turn clamp: no information arrived — settle on the most
            # popular item so the session still ends with one answer
            from agent_lib.query import FreeformQuery

            ranked, _, union_size = freeform_retrieve_with_pool(
                FreeformQuery(), AGENT.index, AGENT.dense, 20, pool_limit=200)
            world_alive = list(ranked)
            pool_size = union_size
            converged = True
            message = ("已達收斂輪次（第 {} 輪）且沒有可用的約束，從全目錄熱門商品中"
                       "選出唯一的最終推薦。").format(session.turn)
            chips = []
    else:
        ranked, pool, union_size = freeform_retrieve_with_pool(accumulated, AGENT.index,
                                                               AGENT.dense, 20, pool_limit=200)
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
            except Exception as exc:
                print(f"[server] chat LLM rerank failed: {exc}", flush=True)
                ordered, usage = None, {"prompt_tokens": 0, "completion_tokens": 0}
            if ordered:
                ranked = ordered + [asin for asin in ranked if asin not in ordered]
        ranked = ranked[:TOP_K]
        # rank over the full union pool (recall quality first); the hard
        # intersection size is reported as the "precisely matched" count
        hard_set = hard_pool(AGENT.index, session.guide)
        is_hard = bool(hard_set)
        pool_size = len(hard_set) if hard_set else union_size
        converged = session.guide.should_converge(pool_size, session.turn)
        clamped = session.turn >= 9 and not session.guide.converged \
            and not NEGATIVE_RE.search(user_message)
        if converged:
            if NEGATIVE_RE.search(user_message):
                # user rejected a small/ambiguous pool: offer a fresh direction
                converged = False
                message = "這些不行的話，換個方向？點一個類別，或直接告訴我你想找什麼："
                chips = [{"type": "category", "label": label, "message": text}
                         for label, text in STARTER_CATEGORIES]
            elif clamped:
                message = (f"已達收斂輪次（第 {session.turn} 輪），在精確符合的 {pool_size} 個候選中"
                           "選出唯一的最終推薦。想換方向直接輸入新需求即可。")
            else:
                message = (f"已收斂：精確符合 {pool_size} 個，選出唯一的最終推薦。"
                           "想換方向直接輸入新需求即可。")
        else:
            facet, values = choose_facet(AGENT.index, pool, session.guide)
            if facet is None or not values:
                converged = True
                message = (f"精確符合 {pool_size} 個，選出唯一的最終推薦。"
                           "想換方向直接輸入新需求即可。")
            else:
                session.guide.guide_rounds += 1
                session.guide.facet_keys.add(facet)
                message = guide_message(pool_size, facet, values)
                chips = option_labels(facet, values)
            if not converged:
                chips.append({"type": "converge", "label": "就這些吧", "message": "就这些吧"})
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
            signals.append(f"關鍵詞×{len(matched_kw)}")
        if accumulated.materials & AGENT.index.material_sets[final_asin]:
            signals.append("材質 ✓")
        if accumulated.colors & AGENT.index.color_sets[final_asin]:
            signals.append("顏色 ✓")
        if accumulated.budget is not None and AGENT.index.prices[final_asin] is not None:
            signals.append(f"預算 ${AGENT.index.prices[final_asin]:g}")
        coarse_key = " ".join(accumulated.text.lower().split())
        if AGENT.index.category_coarse_key.get(final_asin) == coarse_key:
            signals.append("精確類目 ✓")
        if AGENT.dense is not None:
            try:
                sims = AGENT.dense.query_scores(" ".join([*accumulated.keywords,
                                                          *accumulated.materials,
                                                          *accumulated.colors]), [final_asin])
                if sims and sims[0][1] > 0.05:
                    signals.append(f"語義相似 {sims[0][1]:.2f}")
            except Exception:
                pass
        if usage.get("completion_tokens"):
            signals.append("LLM 重排 ✓")
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
                                "error": "本機未找到 DeepSeek 憑證（~/.dsh/.credentials.yaml 或 DEEPSEEK_API_KEY）"}, 400)
                else:
                    self._json({"ok": True, "configured": True, "model": AGENT.llm.model,
                                "source": "local"})
                return
            api_base = str(body.get("api_base") or "").strip()
            api_key = str(body.get("api_key") or "").strip()
            model = str(body.get("model") or "gpt-4o-mini").strip()
            if not api_base or not api_key:
                self._json({"ok": False, "configured": False, "error": "api_base 與 api_key 不能為空"}, 400)
                return
            AGENT.llm = LLMReranker(api_base, api_key, model)
            self._json({"ok": True, "configured": True, "model": model})
        elif self.path == "/mcp":
            # JSON-RPC 2.0 endpoint (same handler as the stdio server)
            ctx = MCPContext(index=AGENT.index, dense=AGENT.dense)
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
    _, CATEGORIES, PRODUCTS = catalog_index(args.catalog)
    SAMPLES = load_jsonl(args.dataset)
    print(f"ready: {len(PRODUCTS)} products, {len(SAMPLES)} public sessions, "
          f"dense={type(AGENT.dense).__name__}", flush=True)

    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    print(f"demo UI: http://127.0.0.1:{args.port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
