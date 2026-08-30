"""Free-form query understanding for the demo chat mode.

The competition simulator always speaks fixed English templates, so the
submission agent only understands those. The demo chat mode lets a human type
anything, so this module adds a lightweight layer:

- English tokens are extracted directly (the catalog is English).
- A small clothing-domain zh->en dictionary maps common Chinese words so
  Chinese input still works for the demo.
- Materials / colors / budget are classified into the same synthetic slots
  the main pipeline uses, so both layers share vocabulary.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

BUDGET_RE = re.compile(r"(?:budget|預算|预算|价格|價格)\D{0,12}?(\d{1,5}(?:\.\d{1,2})?)", re.I)
UNDER_RE = re.compile(r"(?:under|below|less than|不到|以下|以内|以內)\D{0,6}?(\d{1,5}(?:\.\d{1,2})?)", re.I)
RANGE_RE = re.compile(r"(?:budget|預算|预算)\D{0,8}?(\d{1,5})\s*(?:[-~到至])\s*(\d{1,5})", re.I)
ABOVE_RE = re.compile(r"(?:budget|預算|预算)\D{0,8}?(\d{1,5})\D{0,4}?(?:以上|及以上)", re.I)
MATERIAL_RE = re.compile(r"\b(cotton|polyester|nylon|leather|wool|spandex|silk|rayon|fabric|denim|down|fleece)\b", re.I)
COLOR_RE = re.compile(r"\b(black|white|blue|red|pink|green|brown|gray|grey|purple|yellow|orange)\b", re.I)
TOKEN_RE = re.compile(r"[a-z0-9]+", re.I)

STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "but", "by", "for", "from", "i",
    "in", "is", "it", "me", "my", "of", "on", "or", "please", "some", "that",
    "the", "this", "to", "want", "with", "would", "you", "looking", "need",
    "under", "below", "less", "than", "about", "around", "dollar", "dollars",
    "like", "just", "get", "got", "do", "can", "could", "buy",
    "budget", "price", "prices",
    # filler / no-information words (must not count as new constraints)
    "hmm", "hm", "ok", "okay", "fine", "sure", "well", "yes", "yeah", "yep",
    "no", "nope", "thanks", "thank", "please", "um", "uh", "whatever",
    "alright", "right", "good", "know", "don", "dont", "guess", "think",
    "anything", "something", "maybe", "nothing", "want", "would",
    "what", "where", "when", "which", "why", "how", "any", "all", "somewhere",
    "preference", "preferences", "requirement", "requirements", "key",
}

# Chinese keyword -> English tokens (longest patterns match first).
# budget/price are handled by the budget regexes, NOT as keywords.
ZH_EN = [
    ("防水", "waterproof"), ("保暖", "warm"), ("暖和", "warm"), ("轻便", "lightweight"),
    ("輕便", "lightweight"), ("宽松", "loose"), ("寬鬆", "loose"), ("修身", "slim"),
    ("礼物", "gift"), ("禮物", "gift"), ("儿童", "kids"), ("兒童", "kids"),
    ("小孩", "kids"), ("女士", "women"), ("男士", "men"), ("老人", "grandma"),
    ("母亲", "mom"), ("母親", "mom"), ("爸爸", "dad"), ("妈妈", "mom"),
    ("媽媽", "mom"), ("祖母", "grandma"), ("爷爷", "grandpa"), ("聖誕", "christmas"),
    ("老公", "husband"), ("丈夫", "husband"), ("老婆", "wife"), ("妻子", "wife"),
    ("男朋友", "boyfriend"), ("男友", "boyfriend"), ("女朋友", "girlfriend"),
    ("女友", "girlfriend"), ("兄弟", "brother"), ("姐妹", "sister"), ("朋友", "friend"),
    ("同事", "colleague"), ("闺蜜", "best friend"), ("閨蜜", "best friend"),
    ("圣诞", "christmas"), ("婚礼", "wedding"), ("婚禮", "wedding"), ("运动", "sport"),
    ("運動", "sport"), ("跑步", "running"), ("登山", "hiking"), ("滑雪", "skiing"),
    ("健身", "gym"), ("户外", "outdoor"), ("戶外", "outdoor"), ("工作", "work"),
    ("黑色", "black"), ("白色", "white"), ("红色", "red"), ("紅色", "red"),
    ("蓝色", "blue"), ("藍色", "blue"), ("绿色", "green"), ("綠色", "green"),
    ("粉色", "pink"), ("灰色", "grey"), ("紫色", "purple"), ("黄色", "yellow"),
    ("黃色", "yellow"), ("橙色", "orange"), ("棕色", "brown"), ("米色", "beige"),
    ("纯棉", "cotton"), ("純棉", "cotton"), ("涤纶", "polyester"), ("滌綸", "polyester"),
    ("聚酯", "polyester"), ("尼龙", "nylon"), ("尼龍", "nylon"), ("皮革", "leather"),
    ("真皮", "leather"), ("羊毛", "wool"), ("丝绸", "silk"), ("絲綢", "silk"),
    ("真丝", "silk"), ("真絲", "silk"), ("氨纶", "spandex"), ("氨綸", "spandex"),
    ("羽绒", "down"), ("羽絨", "down"), ("牛仔", "denim"), ("法兰绒", "flannel"),
    ("法蘭絨", "flannel"), ("摇粒绒", "fleece"), ("靴子", "boots"), ("雪地靴", "snow boots"),
    ("运动鞋", "sneakers"), ("運動鞋", "sneakers"), ("凉鞋", "sandals"), ("涼鞋", "sandals"),
    ("拖鞋", "slippers"), ("高跟鞋", "heels"), ("球鞋", "sneakers"),
    ("衬衫", "shirt"), ("襯衫", "shirt"), ("T恤", "t-shirt"), ("t恤", "t-shirt"),
    ("卫衣", "hoodie"), ("衛衣", "hoodie"), ("毛衣", "sweater"), ("外套", "jacket"),
    ("大衣", "coat"), ("夹克", "jacket"), ("夾克", "jacket"), ("羽绒服", "down jacket"),
    ("羽絨服", "down jacket"), ("风衣", "trench coat"), ("風衣", "trench coat"),
    ("裤子", "pants"), ("褲子", "pants"), ("牛仔裤", "jeans"), ("牛仔褲", "jeans"),
    ("短裤", "shorts"), ("短褲", "shorts"), ("裙子", "skirt"), ("连衣裙", "dress"),
    ("連衣裙", "dress"), ("腰带", "belt"), ("腰帶", "belt"), ("皮带", "belt"),
    ("皮帶", "belt"), ("帽子", "hat"), ("围巾", "scarf"), ("圍巾", "scarf"),
    ("手套", "gloves"), ("袜子", "socks"), ("襪子", "socks"), ("背包", "backpack"),
    ("钱包", "wallet"), ("錢包", "wallet"), ("手表", "watch"), ("手錶", "watch"),
    ("项链", "necklace"), ("項鏈", "necklace"), ("耳环", "earrings"), ("耳環", "earrings"),
    ("戒指", "ring"), ("手镯", "bracelet"), ("手鐲", "bracelet"), ("内衣", "underwear"),
    ("內衣", "underwear"), ("泳衣", "swim"), ("睡衣", "pajamas"), ("西装", "suit"),
    ("西裝", "suit"), ("领带", "tie"), ("領帶", "tie"), ("眼镜", "glasses"),
    ("眼鏡", "glasses"), ("太阳镜", "sunglasses"), ("太陽鏡", "sunglasses"),
    ("皮靴", "leather boots"), ("皮鞋", "leather shoes"), ("皮质", "leather"),
    ("上衣", "tops"),
    ("鞋", "shoes"),  # bare fallback, matched after compound words
    ("皮", "leather"),  # bare fallback, matched after longer patterns
]


@dataclass
class FreeformQuery:
    text: str = ""
    keywords: list[str] = field(default_factory=list)   # English content tokens
    keyword_weights: dict[str, float] = field(default_factory=dict)  # recency decay
    materials: set[str] = field(default_factory=set)
    colors: set[str] = field(default_factory=set)
    recent_materials: set[str] = field(default_factory=set)  # newest material mention
    recent_colors: set[str] = field(default_factory=set)      # newest color mention
    budget: float | None = None


def _map_chinese(text: str) -> list[str]:
    mapped: list[str] = []
    remaining = text
    # longest pattern first so "羽绒服" beats "羽绒"
    for pattern, tokens in sorted(ZH_EN, key=lambda item: -len(item[0])):
        while pattern in remaining:
            mapped.extend(tokens.split())
            remaining = remaining.replace(pattern, " ", 1)
    return mapped


def freeform_query(text: str) -> FreeformQuery:
    query = FreeformQuery(text=text)
    lowered = text.lower()

    # synthetic slots from both English and mapped Chinese
    query.materials = {m.lower() for m in MATERIAL_RE.findall(lowered)}
    query.colors = {c.lower() for c in COLOR_RE.findall(lowered)}
    for keyword in _map_chinese(lowered):
        if keyword in {"cotton", "polyester", "nylon", "leather", "wool", "spandex",
                       "silk", "rayon", "fabric", "denim", "down", "fleece", "flannel"}:
            query.materials.add(keyword)
        elif keyword in {"black", "white", "blue", "red", "pink", "green", "brown",
                         "gray", "grey", "purple", "yellow", "orange", "beige"}:
            query.colors.add(keyword)
        else:
            query.keywords.append(keyword)

    # budget: "budget around $30" / "预算30美元" / "under $30" / "20到50美元" / "100美元以上"
    range_match = RANGE_RE.search(text)
    if range_match:
        try:
            low, high = float(range_match.group(1)), float(range_match.group(2))
            query.budget = (low + high) / 2.0
        except ValueError:
            pass
    if query.budget is None:
        for pattern in (BUDGET_RE, UNDER_RE, ABOVE_RE):
            match = pattern.search(text)
            if match:
                try:
                    query.budget = float(match.group(1))
                    if pattern is ABOVE_RE:
                        query.budget *= 1.6  # "100以上" -> treat 160 as midpoint proxy
                    break
                except ValueError:
                    pass

    # English content tokens (stopword-filtered, len>=2)
    seen = set(query.keywords)
    for token in TOKEN_RE.findall(lowered):
        if token.isdigit():
            continue
        if len(token) >= 2 and token not in STOPWORDS and token not in seen:
            seen.add(token)
            query.keywords.append(token)

    # materials/colors should not double as generic keywords
    query.keywords = [kw for kw in query.keywords
                      if kw not in query.materials and kw not in query.colors]
    return query
