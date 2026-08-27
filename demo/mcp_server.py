#!/usr/bin/env python3
"""MCP stdio server exposing the Shopping Copilot tools.

Usage (from the repository root, with vendored transformers):

    PYTHONPATH=vendor python3 demo/mcp_server.py --catalog data/catalog.jsonl

Register it in any MCP host (Claude Desktop, Cursor, ...) as a stdio server
with that exact command. All logging goes to stderr; stdout carries only
JSON-RPC messages.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from agent_lib.mcp import build_mcp_context, handle  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--catalog", default=str(ROOT / "data" / "catalog.jsonl"))
    args = parser.parse_args()

    print("[mcp] loading catalog + dense index (one-time)...", file=sys.stderr, flush=True)
    ctx = build_mcp_context(args.catalog)
    print("[mcp] ready — waiting for JSON-RPC messages on stdin", file=sys.stderr, flush=True)

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            request = json.loads(line)
        except json.JSONDecodeError:
            continue
        response = handle(ctx, request.get("method"), request.get("params") or {}, request.get("id"))
        if response is not None:
            sys.stdout.write(json.dumps(response, ensure_ascii=False) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    main()
