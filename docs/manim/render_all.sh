#!/bin/bash
# Render every modular scene to docs/manim/media/final/ at 1080p60.
set -e
MANIM=/Users/faputa/Documents/hackathon/EntroShop/.venv/bin/manim
OUT=media/final
mkdir -p "$OUT"

render() {  # render <file> <scene>
  echo "=== $1 -> $2 ==="
  $MANIM render -qh "$1" "$2" --disable_caching > /tmp/manim_render.log 2>&1 || { echo "FAIL $2"; tail -5 /tmp/manim_render.log; exit 1; }
  src="media/videos/$(basename "$1" .py)/1080p60/$2.mp4"
  if [ -f "$src" ]; then cp "$src" "$OUT/$2.mp4"; else echo "MISSING $src"; fi
}

render convergence.py EntroShopOpen_Cloud
render convergence.py EntroShopOpen_Target
render convergence.py EntroShopOpen_Rings
render convergence.py EntroShopOpen_Collapse
render convergence.py EntroShopOpen_Score
render convergence.py EntroShopOpen_ScoreHit
render convergence.py EntroShopOpen_ScoreTurns
render convergence.py EntroShopOpen_ScoreTokens
render tree.py EntroShopTree_Grow
render tree.py EntroShopTree_Breadcrumb
render tree.py EntroShopTree_Lookup
render numbers.py EntroShopNumbers_Build
render numbers.py EntroShopNumbers_Highlight
render pipeline.py EntroShopPipeline_Build
render pipeline.py EntroShopPipeline_Loop
render convergence_policy.py EntroShopPolicy_Curve
render convergence_policy.py EntroShopPolicy_Wall
render mcp.py EntroShopMCP_Build
render mcp.py EntroShopMCP_Hosts
render scores.py EntroShopScores
render stress.py EntroShopStress_Grid
render stress.py EntroShopStress_Banner
echo "ALL DONE"
