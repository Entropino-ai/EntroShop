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

# "budget around $X" — a synthetic constraint, never a catalog phrase.
BUDGET_RE = re.compile(r"budget around \$([\d.,]+)", re.I)
# "color: x" — a tagged color disclosed as its own unit, not a phrase.
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
    """Structured constraints extracted from one simulator message.

    Each field captures one signal channel the downstream state machine consumes:
    the disclosed category, exact catalog phrases (for conjunction), synthetic
    materials/colors/budget, and control-flow flags that tell the agent how the
    customer's intent is changing (override, retry, no-more, dud, ...). Empty
    fields mean "no such signal in this message", not "unknown".
    """
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
    """Lowercase and split ``value`` into alphanumeric tokens.

    Used only as a cheap heuristic for judging trie-hit plausibility (see
    ``_plausible_phrase``); punctuation and whitespace are discarded, so the
    result is a bag of bare words, not a reconstruction of the original text.
    """
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
    # Bare material word disclosed on its own (e.g. "cotton") → synthetic slot.
    if re.fullmatch(r"cotton|polyester|nylon|leather|wool|spandex|silk|rayon|fabric", lowered):
        result.materials.add(lowered)
        return
    # Bare color word → color slot. fullmatch avoids catching it inside a phrase.
    if re.fullmatch(r"black|white|blue|red|pink|green|brown|gray|grey|purple|yellow|orange", lowered):
        result.colors.add(lowered)
        return
    # Tagged color "color: x" → keep only the word after the colon.
    if re.fullmatch(r"color:\s*[a-z]+", lowered):
        result.colors.add(lowered.split(":", 1)[1].strip())
        return
    # Budget phrase is a synthetic numeric constraint, not a phrase.
    budget_match = BUDGET_RE.fullmatch(lowered)
    if budget_match:
        try:
            # Strip thousands separators so "1,200" parses as 1200.
            result.budget = float(budget_match.group(1).replace(",", ""))
        except ValueError:
            # Malformed number: ignore the budget rather than crash extraction.
            pass
        return
    # Everything else is treated as an exact catalog phrase for conjunction.
    result.phrases.add(value)


def _maximal(phrases: set[str]) -> set[str]:
    """Keep only phrases not contained inside another matched phrase.

    The trie reports every catalog phrase that appears as a substring; short
    sub-phrases of a disclosed constraint (e.g. "Solid colors" inside the full
    fabric-composition string) have tiny, misleading postings and must not
    participate in the conjunction.
    """
    # Longest-first so a containing phrase is always already in ``maximal``
    # when a shorter sub-phrase is tested against it.
    ordered = sorted(phrases, key=len, reverse=True)
    maximal: set[str] = set()
    for phrase in ordered:
        # Drop a phrase if it is a strict substring of an already-kept phrase.
        if any(phrase != other and phrase in other for other in maximal):
            continue
        maximal.add(phrase)
    return maximal


def parse(user_message: str, index: CatalogIndex) -> ParsedMessage:
    """Extract every structured constraint from one simulator message.

    This is the message-understanding entry point: it combines three independent
    channels so no signal is lost when the templates interleave them.

    1. Synthetic constraints — bare material/color words, "color: x" tags, and
       budget figures — are regexed straight out of the text because they are
       never catalog phrases.
    2. Control-flow templates set the intent-change flags (override, dud,
       no-more, retry).
    3. The disclosed category and its constraint payload are split out of the
       fixed opening templates, and each payload fragment is routed via
       ``_add_constraint``.
    4. Finally the phrase trie rescues any catalog phrase that appears verbatim
       but was not captured by the template split, keeping only maximal phrases.

    Returns a ``ParsedMessage`` whose empty fields simply mean "no signal"; the
    function is pure (mutates only its fresh ``result``) and never raises on
    malformed text, so it is safe to call on arbitrary user input.
    """
    result = ParsedMessage()
    text = user_message.strip()

    # --- synthetic constraints (these never live in the phrase index) ---
    # Bare material/color words anywhere in the text, lowercased for matching.
    result.materials = {match.lower() for match in MATERIAL_RE.findall(text)}
    result.colors = {match.lower() for match in COLOR_RE.findall(text)}
    # "color: x" tags add their color even when it is not adjacent to a bare word.
    for match in COLOR_TAG_RE.finditer(text):
        color = match.group(1).lower()
        # Guard: only pure-letter tags qualify, so stray text never pollutes colors.
        if re.fullmatch(r"[a-z]+", color):
            result.colors.add(color)
    # Budget is numeric and free-form ("budget around $X"), so search, not anchor.
    budget_match = BUDGET_RE.search(text)
    if budget_match:
        try:
            result.budget = float(budget_match.group(1).replace(",", ""))
        except ValueError:
            # Unparseable number: leave budget unset rather than failing.
            pass

    # --- control-flow templates ---
    # These flags steer the state machine; they are intent signals, not constraints.
    lowered = text.lower()
    # Override: the customer is replacing their earlier preference.
    if lowered.startswith("actually, ignore my earlier preference"):
        result.is_override = True
    # Dud: the customer declines to constrain this attribute ("use judgment").
    if "i don't have a preference for" in lowered and "use your judgment" in lowered:
        result.is_dud = True
    # No-more: the customer has stopped adding preferences.
    if "i don't have an additional preference" in lowered:
        result.is_no_more = True
    # Retry: the agent guessed wrong and must probe one specific attribute.
    if "not quite right yet" in lowered and "ask me about one specific attribute" in lowered:
        result.is_retry = True

    # --- category phrase (initial messages only) ---
    # The opening template "I'm looking for X ..." carries the coarse category.
    if text.startswith("I'm looking for "):
        rest = text[len("I'm looking for "):]
        # "still exploring" form: category only, no constraint payload yet.
        if ", but I'm still exploring" in rest:
            result.category = rest.split(", but I'm still exploring", 1)[0].strip()
            result.exploring = True
        else:
            # Split at the first sentence boundary: head = category, tail = payload.
            head, sep, tail = rest.partition(". ")
            result.category = head.strip()
            if sep:
                # tail is a constraint-bearing remainder
                constraint_text = tail.strip()
                # Distinguish the two opening variants by their payload preamble.
                if constraint_text.startswith("A key requirement is: "):
                    constraint_text = constraint_text[len("A key requirement is: "):].strip()
                    result.is_buying_opening = True
                else:
                    result.is_override_opening = True
                # Drop a single trailing period so the fragment matches catalog strings.
                constraint_text = constraint_text[:-1] if constraint_text.endswith(".") else constraint_text
                constraint_text = constraint_text.strip()
                if constraint_text:
                    _add_constraint(result, constraint_text)

    # --- "For that, what matters is: X; Y." ---
    marker = "For that, what matters is: "
    if marker in text:
        # Everything after the marker is one or more "; "-joined constraints.
        payload = text.split(marker, 1)[1].strip()
        # Strip the sentence-final period so fragments match verbatim catalog strings.
        if payload.endswith("."):
            payload = payload[:-1]
        for part in payload.split("; "):
            part = part.strip()
            if part:
                _add_constraint(result, part)

    # --- override message: "Actually, ignore ... What I need is: X." ---
    override_marker = "What I need is: "
    if override_marker in text:
        # The override payload is the new constraint that replaces prior ones.
        payload = text.split(override_marker, 1)[1].strip()
        if payload.endswith("."):
            payload = payload[:-1]
        payload = payload.strip()
        if payload:
            _add_constraint(result, payload)

    # --- verbatim phrase lookup: any catalog phrase appearing in the message ---
    # The trie is a substring search over every catalog phrase: it rescues
    # disclosed constraints the template split above may have missed or mangled.
    for phrase in index.phrase_trie.find(text):
        # Skip junk/single-token hits and avoid re-adding template-captured phrases.
        if _plausible_phrase(phrase) and phrase not in result.phrases:
            result.phrases.add(phrase)

    # keep only maximal phrases (sub-phrases have misleading postings)
    result.phrases = _maximal(result.phrases)
    return result
