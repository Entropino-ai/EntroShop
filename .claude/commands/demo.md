---
description: Start the MiroFish swarm demo server on :8090
---

Start the interactive demo server and confirm it is healthy.

1. Run `python3 demo/server.py --port 8090` in the background.
   First launch encodes 50k MiniLM embeddings (~5 min, cached afterwards in
   `data/models/`); subsequent launches are fast.
2. Wait for the `demo UI: http://127.0.0.1:8090` line, then check
   `curl -s http://127.0.0.1:8090/api/health` — expect
   `{"ok": true, "products": 50000, "samples": 200, ...}`.
3. Optionally create a demo session:
   `curl -s -X POST http://127.0.0.1:8090/api/new -H "Content-Type: application/json" -d '{"mode":"demo","scenario":"random"}'`
4. Report the health payload and, if a session was created, the scenario + target.
