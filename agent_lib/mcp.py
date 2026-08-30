"""Minimal Model Context Protocol (MCP) server core (JSON-RPC 2.0, stdlib).

Implements the protocol essentials without the official SDK: initialize
handshake, tools/list, tools/call, ping. Transport-agnostic — the demo HTTP
endpoint (POST /mcp on the demo server) and the stdio entry point
(demo/mcp_server.py) share this module.

Tools exposed to MCP hosts (Claude Desktop, IDE agents, ...):
  search_products   free-form catalog search (Chinese/English, 50k products)
  product_details   full product metadata by parent_asin
  clarify           next clarification question for a shopping conversation
"""
from __future__ import annotations

import json
from dataclasses import dataclass

from .dense import DenseIndex, product_text
from .index import CatalogIndex
from .query import freeform_query
from .retrieve import freeform_retrieve

PROTOCOL_VERSION = "2025-06-18"
SERVER_INFO = {"name": "techjam-shopping-copilot", "version": "1.0.0"}

TOOLS = [
    {
        "name": "search_products",
        "description": (
            "Search a 50,000-product clothing catalog with a free-form query "
            "(Chinese or English). Returns ranked products with parent_asin, "
            "title, price, average_rating, rating_number, categories, store."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "e.g. black leather belt under $30"},
                "top_k": {"type": "integer", "description": "number of results", "default": 10},
            },
            "required": ["query"],
        },
    },
    {
        "name": "product_details",
        "description": "Return full metadata for one product given its parent_asin.",
        "inputSchema": {
            "type": "object",
            "properties": {"asin": {"type": "string", "description": "parent_asin, e.g. B07K34RX5J"}},
            "required": ["asin"],
        },
    },
    {
        "name": "clarify",
        "description": (
            "Given a shopping conversation, suggest the next clarification "
            "question and the attribute to ask about (category, material, "
            "color, size, style, brand, budget, feature, use_case, other)."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {"conversation": {"type": "string"}},
            "required": ["conversation"],
        },
    },
    {
        "name": "tree_chain",
        "description": (
            "Return the unique n-ary property-tree chain of a product: the "
            "category properties from root to leaf (coarse to fine), plus how "
            "many catalog products share that exact leaf chain."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {"asin": {"type": "string", "description": "parent_asin, e.g. B07K34RX5J"}},
            "required": ["asin"],
        },
    },
]


@dataclass
class MCPContext:
    index: CatalogIndex
    dense: object  # TransformerDense or DenseIndex (query_scores interface)
    tree: object | None = None  # optional ProductTree (unique product chains)


def build_mcp_context(catalog_path: str) -> MCPContext:
    """Load the catalog index plus the strongest available dense route."""
    index = CatalogIndex(catalog_path)
    dense: object = None
    try:
        from .dense_transformer import TransformerDense

        texts = {asin: product_text(product) for asin, product in index.products.items()}
        dense = TransformerDense(index.products, texts)
    except Exception as exc:
        print(f"[mcp] MiniLM unavailable ({exc}); falling back to TF-IDF", flush=True)
    if dense is None:
        dense = DenseIndex(index.products)
    return MCPContext(index=index, dense=dense)


def _product_summary(asin: str, index: CatalogIndex) -> dict:
    product = index.products.get(asin, {})
    features = product.get("features") or []
    if isinstance(features, dict):
        feature_list = [f"{key}: {item}" for key, item in features.items()][:3]
    else:
        feature_list = [str(item) for item in features][:3]
    return {
        "parent_asin": asin,
        "title": product.get("title"),
        "price": product.get("price"),
        "average_rating": product.get("average_rating"),
        "rating_number": product.get("rating_number"),
        "categories": product.get("categories"),
        "store": product.get("store"),
        "features": feature_list,
    }


def _call_tool(ctx: MCPContext, name: str, arguments: dict) -> object:
    if name == "search_products":
        query_text = str(arguments.get("query") or "").strip()
        if not query_text:
            raise ValueError("query is required")
        top_k = int(arguments.get("top_k") or 10)
        top_k = max(1, min(top_k, 20))
        parsed = freeform_query(query_text)
        ranked = freeform_retrieve(parsed, ctx.index, ctx.dense, top_k)
        return {
            "results": [_product_summary(asin, ctx.index) for asin in ranked],
            "parsed": {
                "keywords": parsed.keywords,
                "materials": sorted(parsed.materials),
                "colors": sorted(parsed.colors),
                "budget": parsed.budget,
            },
        }
    if name == "product_details":
        asin = str(arguments.get("asin") or "").strip()
        if asin not in ctx.index.products:
            raise ValueError(f"unknown parent_asin: {asin}")
        return _product_summary(asin, ctx.index)
    if name == "clarify":
        conversation = str(arguments.get("conversation") or "")
        parsed = freeform_query(conversation)
        if not parsed.keywords and not parsed.materials and not parsed.colors:
            return {"message": "What kind of product are you looking for?", "ask_attribute": "category"}
        if not parsed.materials:
            return {"message": "Any material preference (cotton, leather, wool...)?", "ask_attribute": "material"}
        if not parsed.colors:
            return {"message": "Any color preference?", "ask_attribute": "color"}
        if parsed.budget is None:
            return {"message": "What budget range are you thinking of?", "ask_attribute": "budget"}
        return {"message": "Any other hard requirements? Otherwise I'll start recommending.", "ask_attribute": None}
    if name == "tree_chain":
        asin = str(arguments.get("asin") or "").strip()
        if asin not in ctx.index.products:
            raise ValueError(f"unknown parent_asin: {asin}")
        if ctx.tree is None:
            from .tree import ProductTree

            ctx.tree = ProductTree(ctx.index)
        chain = ctx.tree.chain(asin)
        return {
            "parent_asin": asin,
            "chain": chain,
            "leaf_products": len(ctx.tree.products_for(chain)),
        }
    raise ValueError(f"unknown tool: {name}")


def handle(ctx: MCPContext, method: str | None, params: dict, request_id) -> dict | None:
    """Dispatch one JSON-RPC request; returns the response dict or None for
    notifications (no id)."""
    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {"tools": {}},
                "serverInfo": SERVER_INFO,
            },
        }
    if method == "notifications/initialized":
        return None
    if method == "ping":
        return {"jsonrpc": "2.0", "id": request_id, "result": {}}
    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": request_id, "result": {"tools": TOOLS}}
    if method == "tools/call":
        name = str((params or {}).get("name") or "")
        arguments = (params or {}).get("arguments") or {}
        try:
            result = _call_tool(ctx, name, arguments)
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {
                    "content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False)}],
                    "isError": False,
                },
            }
        except Exception as exc:
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {
                    "content": [{"type": "text", "text": f"error: {exc}"}],
                    "isError": True,
                },
            }
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "error": {"code": -32601, "message": f"method not found: {method}"},
    }
