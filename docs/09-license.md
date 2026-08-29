# 09 · License & credits

## License

The EntroShop source code is released under the **MIT License** (see the
repository `LICENSE` file). The MIT license is a permissive open-source
license: you may use, copy, modify, merge, publish, distribute, sublicense,
and sell copies of the software, provided the copyright notice and permission
notice are included in all copies or substantial portions.

**Note on competition data:** the catalog, evaluator, and public set are the
organizers' property (TikTok TechJam 2026 participant kit). They are **not**
distributed in this repository — the setup instructions in
[01 · Getting started](01-getting-started.md) download them from the
official participant-kit release. Treat them under the competition's terms.

## Credits

- **Data:** Amazon Reviews 2023, `Clothing_Shoes_and_Jewelry` subset
  (McAuley Lab, amazon-reviews-2023.github.io).
- **Task & evaluator:** TikTok TechJam 2026 Track 4, *Shopping Copilot: AI
  Conversational Search & Recommendations*.
- **Design references:**
  - Lei et al., *Estimation–Action–Reflection*, WSDM 2020.
  - Sekulić et al., *Evaluating Mixed-initiative Conversational Search
    Systems via User Simulation*, SIGIR 2022.
  - Yao et al., *ReAct*, ICLR 2023.
  - Bocha-Labs, *MiroFish* swarm-intelligence engine (UI metaphor).
  - Genesis / Blender-style documentation structure.
- **Optional model:** MiniLM `all-MiniLM-L6-v2` (sentence-transformers) for
  the dense route; DeepSeek (OpenAI-compatible) for the optional reranker.
