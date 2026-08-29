# Demonstrated Multi-Turn Session

Two sessions replayed through the official evaluator protocol on the public
development set. The agent never sees the ground truth, the intent card, or the
simulator state; the customer policy is the deterministic simulator policy from
the organizer kit. The ground truth is shown here only for review.

Reproduce:

```bash
git clone https://github.com/TechJam2026/techjam-conversational-search.git
# download data/catalog.jsonl and data/public_set.jsonl from the participant kit
python3 -m evaluator.local_evaluator        # full 200-session run
```

---

## Session 1 (main): boundary scenario, hit in 3 turns at rank 1

**Sample:** `public_0180` · **Scenario:** boundary (customer has no preference
for the first attribute asked, 5% of the official mix)
**Ground truth (hidden):** Saucony Women's Cohesion 10 Running Shoe · `B01HSMYV8E`

### Turn 1

- Customer: "I'm looking for Shoes Fashion Sneakers, but I'm still exploring."
- Agent asks: `other`
- Agent says: "Anything else you'd like to narrow down — material, color, budget, or a particular feature?"
- Top recommendations:
  1. Skechers Sport Women's Elite Synergy Fashion Sneaker · `B00TT6TY6M`
  2. Skechers Sport Women's Hot Ticket Fashion Sneaker · `B003B345O0`
  3. ZBRO Women's Muffin Rhinestone New Crystal Platform Sneakers · `B098M5CW2F`
  4. Blowfish Malibu Women's Fruit Sneaker · `B07B5RGY2N`
  5. Concept 3 by Skechers Women's Evve Fashion Slip-on Sneaker · `B07YFG1NGD`

### Turn 2

- Customer: "I don't have a preference for other; please use your judgment."
- Agent asks: `other` (asks again instead of giving up on the no-preference reply)
- Agent says: "Anything else you'd like to narrow down — material, color, budget, or a particular feature?"
- Top recommendations:
  1. Skechers Sport Women's Elite Synergy Fashion Sneaker · `B00TT6TY6M`
  2. ZBRO Women's Muffin Rhinestone New Crystal Platform Sneakers · `B098M5CW2F`
  3. Skechers Sport Women's Hot Ticket Fashion Sneaker · `B003B345O0`
  4. Blowfish Malibu Women's Fruit Sneaker · `B07B5RGY2N`
  5. Concept 3 by Skechers Women's Evve Fashion Slip-on Sneaker · `B07YFG1NGD`

### Turn 3

- Customer: "For that, what matters is: 100% Mesh; Imported."
- Agent asks: `other`
- Agent says: "Anything else you'd like to narrow down — material, color, budget, or a particular feature?"
- Top recommendations:
  1. **Saucony Women's Cohesion 10 Running Shoe · `B01HSMYV8E`** ← HIT, rank 1
  2. Skechers Performance Women's Go Run Ride Ultra Fashion Sneaker · `B009ZDEM66`
  3. Skechers Performance Women's Go Ride Recovery Fashion Sneaker · `B00A64F6U4`
  4. Mark Nason Los Angeles Men's Summershade Fashion Sneaker · `B01BLYDSFW`
  5. Skechers Sport Women's Equalizer 4 · `B00GK61KXY`

**Result: HIT at turn 3, rank 1.** The customer starts vague, declines the
first clarification, and the agent recovers by re-asking; the moment the
disclosed constraints arrive, the exact target jumps to rank 1.

---

## Session 2 (bonus): buying scenario, the historically hard case

**Sample:** `public_0020` · **Scenario:** buying
**Ground truth (hidden):** Funny Saying Novelty Gift ideas - My Favorite People
Call Me Grandma Long Sleeve T-Shirt · `B08P4SSFX4`

This sample previously pooled 459 candidates from the disclosed constraints
alone (the target shares generic feature strings with hundreds of products).
The exact coarse-category match described in `docs/PROJECT.md` collapsed that
pool, and the session now converts in 2 turns.

### Turn 1

- Customer: "I'm looking for Novelty Women. A key requirement is: cotton."
- Agent asks: `other`
- Agent says: "Anything else you'd like to narrow down — material, color, budget, or a particular feature?"
- Top recommendations: MASH 4077th T-Shirt, Nawoshow Slouchy Sweatshirt, two Custom T Shirt variants, Stephen King Ultra Cotton T-Shirt (target not yet in top 5)

### Turn 2

- Customer: "For that, what matters is: color: grey; Solid colors: 100% Cotton; Heather Grey: 90% Cotton, 10% Polyester; All Other Heathers: 50% Cotton, 50% Polyester."
- Agent asks: `other`
- Agent says: "Anything else you'd like to narrow down — material, color, budget, or a particular feature?"
- Top recommendations:
  1. Black Cat Blue Green T Shirt Designed By Cats Made Better · `B06WP3B6QY`
  2. Post Heart Surgery Bypass Recovery Tshirt Open Heart Warrior · `B074X6Q6GG`
  3. Free-ish Since 1865 Black Pride Black History Month T-Shirt · `B0758CQZRM`
  4. Blessed Grandma Mothers Day Grandmother Mother T-Shirt · `B0773HHV2Q`
  5. **Funny Saying Novelty Gift ideas - My Favorite People Call Me Grandma Long Sleeve T-Shirt · `B08P4SSFX4`** ← HIT, rank 5

**Result: HIT at turn 2, rank 5.**

---

Both sessions are deterministic replays: same inputs, same outputs, 0 API
tokens, no network.
