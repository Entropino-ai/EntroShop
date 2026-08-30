# EntroShop Documentation

> **Entropy-guided conversational shopping.** Every turn the agent asks the
> highest-information question, narrows the candidate pool, and converges to
> one product within a bounded interaction budget.

This is the official documentation for EntroShop, the TikTok TechJam 2026
Track 4 submission. It is organized like a conventional open-source project:
each chapter lives in its own file and covers one concern, so you can read
top-down or jump straight to the topic you need.

## Table of contents

| # | Chapter | What it covers |
|---|---------|----------------|
| 01 | [Getting started](01-getting-started.md) | Installation, data, running the evaluator and the demo UI |
| 02 | [Architecture](02-architecture.md) | Pipeline overview, routing, and the information-elicitation loop |
| 03 | [Modules](03-modules.md) | Per-module responsibility and public interfaces |
| 04 | [Policy optimization](04-policy-optimization.md) | Offline RL-style search over ask / guidance policies |
| 05 | [Benchmarks](05-benchmarks.md) | Official scores, ablations, and scenario breakdown |
| 06 | [Testing](06-testing.md) | Test suite, smoke tests, and the synthetic stress battery |
| 07 | [FAQ](07-faq.md) | Design rationale, generalization, and known limitations |
| 08 | [Contributing](08-contributing.md) | Dev workflow, conventions, and how to run experiments |
| 09 | [License & credits](09-license.md) | Licensing and attribution |

The competition write-up (mini-paper) lives in
[`PROJECT.md`](PROJECT.md); the standalone stress-test report is in
[`STRESS_TEST.md`](STRESS_TEST.md). The demo-video script (English,
Houdini-Foundations-style walkthrough, covers the core loop and the MCP
server) is in [`DEMO_VIDEO_SCRIPT.md`](DEMO_VIDEO_SCRIPT.md); its
line-by-line storyboard with Manim scenes is in
[`DEMO_VIDEO_STORYBOARD.md`](DEMO_VIDEO_STORYBOARD.md) (renderable
scenes under [`manim/`](manim/)); the multi-turn session it can record
is specified in [`DEMO_SESSION.md`](DEMO_SESSION.md).

## Reader's guide

- **Judges / reviewers** — read [01](01-getting-started.md) for a quick
  reproduction, [02](02-architecture.md) and [04](04-policy-optimization.md)
  for the method, [05](05-benchmarks.md) for the numbers.
- **Developers** — read [03](03-modules.md), [06](06-testing.md), and
  [08](08-contributing.md).
- **Users of the demo** — start with [01](01-getting-started.md) → *Run the
  demo UI*, then see the feature list in [02](02-architecture.md).
