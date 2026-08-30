#!/usr/bin/env python3
"""MCP stdio server exposing the Shopping Copilot tools.

This thin entry point turns the offline Shopping Copilot into a Model Context
Protocol (MCP) server so any MCP host (Claude Desktop, Cursor, ...) can drive
the entropy-guided conversational search loop over stdio. It exists because MCP
hosts speak newline-delimited JSON-RPC over the process's stdin/stdout, which is
the only transport contract this file implements.

Usage (from the repository root, with vendored transformers):

    PYTHONPATH=vendor python3 demo/mcp_server.py --catalog data/catalog.jsonl

Register it in any MCP host (Claude Desktop, Cursor, ...) as a stdio server
with that exact command.

Contract / failure modes:
- All logging goes to stderr; stdout carries ONLY JSON-RPC messages (one JSON
  object per line, newline-terminated, flushed immediately), because any stray
  text on stdout corrupts the MCP framing and breaks the host connection.
- The dense index is built once at startup (potentially slow); everything after
  the "ready" banner is a request/response loop with no per-request index work.
- Malformed input lines (blank lines, non-JSON) are silently skipped so a stray
  log or partial write on stdin cannot crash the server.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Resolve the repository root (parent of demo/) independent of the caller's cwd,
# so the script runs correctly no matter where the host launches it from.
ROOT = Path(__file__).resolve().parents[1]
# Make the repo root importable so `agent_lib` resolves without packaging/install.
sys.path.insert(0, str(ROOT))

from agent_lib.mcp import build_mcp_context, handle  # noqa: E402


def main() -> None:
    """Run the MCP stdio server loop.

    Parses CLI args, builds the shared MCP context (loading the catalog and
    dense index exactly once), then blocks reading newline-delimited JSON-RPC
    requests from stdin and writing responses to stdout until the host closes
    stdin (EOF ends the loop and the process exits cleanly).

    Contract:
    - The catalog path defaults to `<repo>/data/catalog.jsonl` and can be
      overridden via `--catalog`.
    - `ctx` is built once and reused for every request; it must not be rebuilt
      per request because the dense index is expensive to construct.
    - Notification-style messages (no `id`, e.g. `notifications/initialized`)
      yield a `None` response and are deliberately not answered.
    """
    parser = argparse.ArgumentParser()
    parser.add_argument("--catalog", default=str(ROOT / "data" / "catalog.jsonl"))
    args = parser.parse_args()

    # Progress banners go to stderr so stdout stays a clean JSON-RPC stream.
    print("[mcp] loading catalog + dense index (one-time)...", file=sys.stderr, flush=True)
    ctx = build_mcp_context(args.catalog)
    print("[mcp] ready — waiting for JSON-RPC messages on stdin", file=sys.stderr, flush=True)

    for line in sys.stdin:
        line = line.strip()  # Tolerate leading/trailing whitespace in the framing line.
        if not line:
            continue  # Skip blank keep-alive/whitespace lines without erroring.
        try:
            request = json.loads(line)
        except json.JSONDecodeError:
            continue  # Ignore non-JSON noise; a partial write must not kill the loop.
        # `params` may be absent or null; normalize to {} so `handle` always
        # receives a dict. `id` may be None for notifications.
        response = handle(ctx, request.get("method"), request.get("params") or {}, request.get("id"))
        if response is not None:
            # ensure_ascii=False keeps UTF-8 (Chinese/English) readable in the frame.
            sys.stdout.write(json.dumps(response, ensure_ascii=False) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    main()
