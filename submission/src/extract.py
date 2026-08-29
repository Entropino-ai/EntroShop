"""Message understanding: turn simulator messages into structured constraints.

Two independent channels, combined:
1. Template parsing (messages come from fixed deterministic templates).
2. Trie substring lookup (disclosed constraints appear verbatim in the message
   because the simulator copies them out of the target product's intent card).
Plus regexes for synthetic constraints (bare material words, "color: x", budget).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from .index import MATERIAL_RE, COLOR_RE, CatalogIndex, clean_constraint

BUDGET_RE = re.compile(r"budget around \$([\d.,]+)", re.I)
COLOR_TAG_RE = re.compile(r"color:\s*([a-z]+)", re.I)
# words that may appear in templates but are never product content
TEMPLATE_JUNK = {
    "other", "others", "looking", "exploring", "preference", "preferences",
    "requirement", "requirements", "judgment", "options", "quite", "right",
    "specific", "attribute", "additional", "earlier", "actually", "ignore",
    "what", "need", "needs", "matters", "that", "for", "the", "this", "your",
    "have", "has", "don", "not", "yet", "ask", "about", "one", "please",
    "use", "still", "key", "is", "i", "my", "you",
}


@dataclass
class ParsedMessage:
    category: str = ""
    phrases: set[str] = field(default_factory=set)          # exact catalog phrases
    materials: set[str] = field(default_factory=set)         # bare material words
    colors: set[str] = field(default_factory=set)            # color words
    budget: float | None = None
    is_override: bool = False
    is_override_opening: bool = False                        # opening bare preference
    is_buying_opening: bool = False                          # "A key requirement is:"
    is_dud: bool = False                                     # "no preference, use judgment"
    is_no_more: bool = False                                 # "no additional preference"
    is_retry: bool = False                                   # "not quite right, ask attribute"
    exploring: bool = False


def _tokens(value: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", value.lower())


def _plausible_phrase(phrase: str) -> bool:
    """Reject template junk and single-token noise from the trie lookup.

    Template parsing already captures authoritative constraints (including
    single-token ones like "Imported"), so the trie only needs to rescue
    multi-token phrases that get split by "; " inside the templates.
    """
    tokens = _tokens(phrase)
    if not tokens:
        return False
    if len(tokens) == 1:
        return False
    if all(token in TEMPLATE_JUNK for token in tokens):
        return False
    return True


def _add_constraint(result: ParsedMessage, value: str) -> None:
    """Route a disclosed constraint to the right slot.

    A bare material word ("cotton"), a bare color word, a "color: x" tag, or a
    budget phrase is a synthetic constraint, not an exact catalog phrase;
    adding it to the phrase set would poison exact-phrase conjunction.
    """
    value = clean_constraint(value)
    if not value:
        return
    lowered = value.lower()
    if re.fullmatch(r"cotton|polyester|nylon|leather|wool|spandex|silk|rayon|fabric", lowered):
        result.materials.add(lowered)
        return
    if re.fullmatch(r"black|white|blue|red|pink|green|brown|gray|grey|purple|yellow|orange", lowered):
        result.colors.add(lowered)
        return
    if re.fullmatch(r"color:\s*[a-z]+", lowered):
        result.colors.add(lowered.split(":", 1)[1].strip())
        return
    budget_match = BUDGET_RE.fullmatch(lowered)
    if budget_match:
        try:
            result.budget = float(budget_match.group(1).replace(",", ""))
        except ValueError:
            pass
        return
    result.phrases.add(value)


def _maximal(phrases: set[str]) -> set[str]:
    """Keep only phrases not contained inside another matched phrase.

    The trie reports every catalog phrase that appears as a substring; short
    sub-phrases of a disclosed constraint (e.g. "Solid colors" inside the full
    fabric-composition string) have tiny, misleading postings and must not
    participate in the conjunction.
    """
    ordered = sorted(phrases, key=len, reverse=True)
    maximal: set[str] = set()
    for phrase in ordered:
        if any(phrase != other and phrase in other for other in maximal):
            continue
        maximal.add(phrase)
    return maximal


def parse(user_message: str, index: CatalogIndex) -> ParsedMessage:
    result = ParsedMessage()
    text = user_message.strip()

    # --- synthetic constraints (these never live in the phrase index) ---
    result.materials = {match.lower() for match in MATERIAL_RE.findall(text)}
    result.colors = {match.lower() for match in COLOR_RE.findall(text)}
    for match in COLOR_TAG_RE.finditer(text):
        color = match.group(1).lower()
        if re.fullmatch(r"[a-z]+", color):
            result.colors.add(color)
    budget_match = BUDGET_RE.search(text)
    if budget_match:
        try:
            result.budget = float(budget_match.group(1).replace(",", ""))
        except ValueError:
            pass

    # --- control-flow templates ---
    lowered = text.lower()
    if lowered.startswith("actually, ignore my earlier preference"):
        result.is_override = True
    if "i don't have a preference for" in lowered and "use your judgment" in lowered:
        result.is_dud = True
    if "i don't have an additional preference" in lowered:
        result.is_no_more = True
    if "not quite right yet" in lowered and "ask me about one specific attribute" in lowered:
        result.is_retry = True

    # --- category phrase (initial messages only) ---
    if text.startswith("I'm looking for "):
        rest = text[len("I'm looking for "):]
        if ", but I'm still exploring" in rest:
            result.category = rest.split(", but I'm still exploring", 1)[0].strip()
            result.exploring = True
        else:
            head, sep, tail = rest.partition(". ")
            result.category = head.strip()
            if sep:
                # tail is a constraint-bearing remainder
                constraint_text = tail.strip()
                if constraint_text.startswith("A key requirement is: "):
                    constraint_text = constraint_text[len("A key requirement is: "):].strip()
                    result.is_buying_opening = True
                else:
                    result.is_override_opening = True
                constraint_text = constraint_text[:-1] if constraint_text.endswith(".") else constraint_text
                constraint_text = constraint_text.strip()
                if constraint_text:
                    _add_constraint(result, constraint_text)

    # --- "For that, what matters is: X; Y." ---
    marker = "For that, what matters is: "
    if marker in text:
        payload = text.split(marker, 1)[1].strip()
        if payload.endswith("."):
            payload = payload[:-1]
        for part in payload.split("; "):
            part = part.strip()
            if part:
                _add_constraint(result, part)

    # --- override message: "Actually, ignore ... What I need is: X." ---
    override_marker = "What I need is: "
    if override_marker in text:
        payload = text.split(override_marker, 1)[1].strip()
        if payload.endswith("."):
            payload = payload[:-1]
        payload = payload.strip()
        if payload:
            _add_constraint(result, payload)

    # --- verbatim phrase lookup: any catalog phrase appearing in the message ---
    for phrase in index.phrase_trie.find(text):
        if _plausible_phrase(phrase) and phrase not in result.phrases:
            result.phrases.add(phrase)

    # keep only maximal phrases (sub-phrases have misleading postings)
    result.phrases = _maximal(result.phrases)
    return result
