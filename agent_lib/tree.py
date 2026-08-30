"""ProductTree — an n-ary tree over product properties.

Every fork node carries one product property (a category segment). Children
branch by *containment*: a parent property contains its children, so deeper
levels are progressively finer-grained properties. A mapping lives on the
tree: each node's `products` list maps that property (or the exact chain
down to it) to the concrete catalog products it covers.

Each product is represented by exactly one chain in the tree: the sequence
of category segments from the root down to the product's own category path.
Because a product's `categories` field is a fixed ordered list, that chain
is unique — `chain(asin)` returns it, and `products_for(chain)` recovers
every product sharing it. Two products with the same chain are information-
equivalent at the category level (the "family-ambiguous" corner case), and
their longest common chain is exactly the shared disclosure prefix.

```
root
 └─ Clothing, Shoes & Jewelry          (coarsest property)
     ├─ Women
     │   ├─ Shoes
     │   │   ├─ Boots & Booties        (finer)
     │   │   │   └─ products: [B0…, B1…]   ← concrete products
     │   │   └─ Sneakers
     │   └─ Dresses
     └─ Men
```

The tree is built once from the frozen catalog and is read-only afterwards.
"""
from __future__ import annotations

from typing import Iterator

from .index import CatalogIndex


class _Node:
    """One property node of the tree."""

    __slots__ = ("value", "parent", "children", "products", "_depth", "_subtree")

    def __init__(self, value: str, parent: "_Node | None" = None) -> None:
        self.value = value
        self.parent = parent
        self.children: dict[str, _Node] = {}
        self.products: list[str] = []
        self._depth = (parent._depth + 1) if parent is not None else 0
        self._subtree: set[str] | None = None  # lazily filled; tree is read-only

    @property
    def depth(self) -> int:
        return self._depth

    def is_leaf(self) -> bool:
        return not self.children

    def chain(self) -> list[str]:
        """Node values from the root down to (and including) this node."""
        nodes: list[str] = []
        node: _Node | None = self
        while node is not None:
            nodes.append(node.value)
            node = node.parent
        nodes.reverse()
        return nodes

    def subtree_products(self) -> set[str]:
        """Every product under this node (its own plus all descendants).
        Cached after first call: the tree is built once and read-only."""
        if self._subtree is None:
            out = set(self.products)
            for child in self.children.values():
                out |= child.subtree_products()
            self._subtree = out
        return self._subtree


class ProductTree:
    """n-ary tree over catalog category properties with a product mapping.

    Parameters
    ----------
    index : CatalogIndex
        A built catalog index; the tree reads `index.products`.
    root_label : str
        Label of the synthetic root node (default "catalog").
    """

    def __init__(self, index: CatalogIndex, root_label: str = "catalog") -> None:
        self.root = _Node(root_label)
        self._chain_to_node: dict[tuple[str, ...], _Node] = {}
        self._asin_chain: dict[str, tuple[str, ...]] = {}
        # value_index: normalized property token -> nodes whose value
        # contains that token, so a keyword ("boots") finds every node
        # ("Boots & Booties", "Hiking Boots", ...) in O(1).
        self.value_index: dict[str, list[_Node]] = {}
        self._build(index.products)

    # ------------------------------------------------------------------ build
    # Universal root segments of every category path ("Clothing, Shoes &
    # Jewelry" and friends). They are kept in the tree structure (chains stay
    # complete) but their tokens are NOT indexed: searching "shoes" must hit
    # the real "Shoes" segment, not the root breadcrumb, or every keyword
    # would match the whole catalog.
    ROOT_SEGMENTS = {
        "clothing, shoes & jewelry",
        "clothing, shoes & jewellery",
        "clothing shoes & jewelry",
        "costumes & accessories",
        "novelty & special use",
        "sports fan shop",
        "clothing & accessories",
        "under $25",
        "luxury beauty",
    }

    @staticmethod
    def _normalize_token(token: str) -> str:
        return token.lower().replace("&", "").replace(",", "").strip()

    def _index_node(self, node: _Node) -> None:
        if node.value.lower().strip() in self.ROOT_SEGMENTS:
            return  # universal breadcrumb segment: keep structure, skip index
        for token in node.value.split():
            token = self._normalize_token(token)
            if token:
                self.value_index.setdefault(token, []).append(node)

    def _build(self, products: dict) -> None:
        self._index_node(self.root)
        for asin, product in products.items():
            categories = [str(v) for v in product.get("categories") or []]
            if not categories:
                # products without a category path still need a unique chain:
                # hang them directly under the root, keyed by asin
                categories = [f"__no_category__/{asin}"]
            node = self.root
            path: list[str] = []
            for segment in categories:
                path.append(segment)
                child = node.children.get(segment)
                if child is None:
                    child = _Node(segment, parent=node)
                    node.children[segment] = child
                    self._index_node(child)
                node = child
            node.products.append(asin)
            chain = tuple(path)
            self._chain_to_node.setdefault(chain, node)
            self._asin_chain[asin] = chain

    # ------------------------------------------------------------------ query
    def chain(self, asin: str) -> list[str]:
        """The unique property chain representing this product."""
        return list(self._asin_chain.get(asin, (self.root.value,)))

    def node_for(self, chain: list[str] | tuple[str, ...]) -> _Node | None:
        """The node identified by an exact root-to-node chain, or None."""
        return self._chain_to_node.get(tuple(chain))

    def products_for(self, chain: list[str] | tuple[str, ...]) -> list[str]:
        """Concrete products whose chain is exactly this one (mapping)."""
        node = self.node_for(chain)
        return list(node.products) if node is not None else []

    def products_under(self, chain: list[str] | tuple[str, ...]) -> set[str]:
        """Every product under a property chain (its node + descendants)."""
        node = self.node_for(chain)
        return node.subtree_products() if node is not None else set()

    def common_prefix(self, asin_a: str, asin_b: str) -> list[str]:
        """Longest shared chain prefix of two products (LCA in the tree)."""
        a, b = self.chain(asin_a), self.chain(asin_b)
        prefix: list[str] = []
        for x, y in zip(a, b):
            if x != y:
                break
            prefix.append(x)
        return prefix

    # ------------------------------------------------------- tree-first match
    @staticmethod
    def _variants(keyword: str) -> set[str]:
        """Plural/normalized forms of a keyword for index lookups."""
        base = keyword.lower()
        variants = {base, base + "s", base + "es"}
        if base.endswith("y"):
            variants.add(base[:-1] + "ies")
        if base.endswith("f"):
            variants.add(base[:-1] + "ves")
        if base.endswith("fe"):
            variants.add(base[:-2] + "ves")
        return {v for v in variants if v}

    @staticmethod
    def variants(keyword: str) -> set[str]:
        """Public alias of ``_variants`` (used by retrievers to keep the
        category-bonus scoring aligned with tree-matched chains)."""
        return ProductTree._variants(keyword)

    def subtree_for_keyword(self, keyword: str) -> set[str]:
        """Products under every node whose property matches the keyword
        (token-level, with plural variants). This is the tree-first category
        route: one O(1) index lookup per variant instead of scanning token
        postings. Empty set when no node matches."""
        out: set[str] = set()
        for variant in self._variants(keyword):
            for node in self.value_index.get(variant, []):
                out |= node.subtree_products()
        return out

    def subtree_for_keywords(self, keywords: list[str]) -> tuple[set[str], set[str]]:
        """Tree-first category candidates for a keyword list.

        Returns ``(union, hits)`` where ``union`` is the set of products
        whose chain contains any keyword, and ``hits`` is the set of
        keywords that matched at least one tree node. Keywords without any
        tree node are *not* in ``hits`` — callers fall back to the token
        route for those.
        """
        union: set[str] = set()
        hits: set[str] = set()
        for keyword in keywords:
            products = self.subtree_for_keyword(keyword)
            if products:
                union |= products
                hits.add(keyword)
        return union, hits

    # ------------------------------------------------------------------ stats
    @property
    def node_count(self) -> int:
        return len(self._chain_to_node) + 1  # + root

    @property
    def leaf_count(self) -> int:
        return sum(1 for n in self._chain_to_node.values() if n.is_leaf())

    def depth_histogram(self) -> dict[int, int]:
        hist: dict[int, int] = {}
        for node in self._chain_to_node.values():
            hist[node.depth] = hist.get(node.depth, 0) + 1
        return dict(sorted(hist.items()))

    def families(self, min_size: int = 2) -> list[tuple[list[str], int]]:
        """Chains shared by >= min_size products (the ambiguous families)."""
        return sorted(
            ((list(chain), len(node.products)) for chain, node in
             self._chain_to_node.items() if len(node.products) >= min_size),
            key=lambda item: -item[1],
        )

    # ------------------------------------------------------------------ iter
    def iter_nodes(self) -> Iterator[_Node]:
        stack = [self.root]
        while stack:
            node = stack.pop()
            yield node
            stack.extend(node.children.values())

    def to_dict(self, node: _Node | None = None, limit: int | None = None) -> dict:
        """Serializable tree for the demo UI.

        ``limit`` bounds children per node so a huge tree stays renderable.
        """
        node = node or self.root
        out: dict = {
            "value": node.value,
            "depth": node.depth,
            "product_count": len(node.products),
            "total_products": len(node.subtree_products()),
        }
        children = list(node.children.values())
        if limit is not None:
            children = children[:limit]
        if children:
            out["children"] = [self.to_dict(c, limit) for c in children]
        elif node.products:
            out["products"] = node.products[:10]
        return out
