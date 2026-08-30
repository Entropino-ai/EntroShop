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

import math
from typing import Iterator

from .index import CatalogIndex

# token cache for chain segments (chain values repeat heavily across the
# catalog; caching keeps depth-weighted scoring O(1) per segment)
_segment_token_cache: dict[str, frozenset[str]] = {}


class _Node:
    """One property node of the tree.

    A node stores a single category segment as its ``value`` and links to its
    ``parent`` and ``children``, so the whole tree is an n-ary containment
    hierarchy. ``products`` holds the catalog ASINs mapped to this exact node.
    ``_subtree`` and ``_size`` are lazily computed aggregate caches: the tree
    is built once and never mutated afterwards, so caching is safe and makes
    repeated subtree queries O(1) after their first call.
    """

    __slots__ = ("value", "parent", "children", "products", "_depth", "_subtree", "_size")

    def __init__(self, value: str, parent: "_Node | None" = None) -> None:
        """Create a node; depth is derived from the parent (root has depth 0)."""
        self.value = value
        self.parent = parent
        self.children: dict[str, _Node] = {}
        self.products: list[str] = []
        # depth = parent depth + 1, so the root is 0 and every node's depth is
        # its distance from the root along parent pointers
        self._depth = (parent._depth + 1) if parent is not None else 0
        self._subtree: set[str] | None = None  # lazily filled; tree is read-only
        self._size: int | None = None

    @property
    def depth(self) -> int:
        """Distance from the root (root is 0), precomputed at construction."""
        return self._depth

    def is_leaf(self) -> bool:
        """True when this node has no children (a deepest category segment)."""
        return not self.children

    def chain(self) -> list[str]:
        """Node values from the root down to (and including) this node.

        Walks parent pointers upward (the cheap direction given the tree only
        stores parent links), then reverses so callers get root-first order.
        """
        nodes: list[str] = []
        node: _Node | None = self
        # climb parent pointers to the root, then reverse for root-first order
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
            # union this node's own products with every descendant's products
            for child in self.children.values():
                out |= child.subtree_products()
            self._subtree = out
        return self._subtree

    def subtree_size(self) -> int:
        """Number of concrete products under this node (its own plus all
        descendants). O(1) after first call; no set materialization."""
        if self._size is None:
            total = len(self.products)
            # sum own products plus each child's subtree count
            for child in self.children.values():
                total += child.subtree_size()
            self._size = total
        return self._size


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
        """Build the tree from the catalog and populate the query mappings.

        Creates the synthetic root, then ``_build`` walks every product's
        category path to construct the node hierarchy and fill the three lookup
        structures: ``_chain_to_node`` (chain -> node), ``_asin_chain``
        (asin -> chain) and ``value_index`` (token -> nodes). The tree is
        immutable after construction.
        """
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
        """Lowercase a token and strip separators so index lookups are stable.

        Removing ``&`` and ``,`` makes "Shoes & Boots" and "Shoes, Boots"
        tokenize identically; callers and the index use the same form, so a
        keyword can be matched against compound segment text reliably.
        """
        # lowercase then drop ampersands/commas and surrounding whitespace
        return token.lower().replace("&", "").replace(",", "").strip()

    def _index_node(self, node: _Node) -> None:
        """Add a node's property tokens to ``value_index`` for keyword lookup.

        Each whitespace-separated token of the node's value becomes a key that
        maps to every node containing it. Universal breadcrumb segments are
        deliberately skipped so a generic token like "shoes" cannot match the
        whole catalog through the root breadcrumb.
        """
        if node.value.lower().strip() in self.ROOT_SEGMENTS:
            return  # universal breadcrumb segment: keep structure, skip index
        # split multi-word values into individual tokens ("Boots & Booties")
        for token in node.value.split():
            token = self._normalize_token(token)
            if token:
                self.value_index.setdefault(token, []).append(node)

    def _build(self, products: dict) -> None:
        """Construct the node hierarchy from the catalog's category paths.

        For each product, walk its ordered ``categories`` list and create (or
        reuse) one node per segment, so identical prefixes share nodes. The
        final node records the ASIN as a concrete product, and both the
        chain -> node and asin -> chain maps are filled for later queries.
        """
        self._index_node(self.root)
        for asin, product in products.items():
            categories = [str(v) for v in product.get("categories") or []]
            if not categories:
                # products without a category path still need a unique chain:
                # hang them directly under the root, keyed by asin
                categories = [f"__no_category__/{asin}"]
            node = self.root
            path: list[str] = []
            # walk/create the chain one segment at a time, reusing existing nodes
            for segment in categories:
                path.append(segment)
                child = node.children.get(segment)
                if child is None:
                    child = _Node(segment, parent=node)
                    node.children[segment] = child
                    self._index_node(child)  # index only newly created nodes
                node = child
            node.products.append(asin)
            chain = tuple(path)
            # first chain wins the node reference; later identical chains share it
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
        # zip stops at the shorter chain; break at the first divergence
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
        # handle irregular-ish plurals so a keyword matches differently-spelled
        # segment tokens ("berry" vs "berries", "knife" vs "knives", ...)
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

    def depth_weighted_bonus(self, asin: str, tokens: set[str]) -> float:
        """Binary-search contribution of a product's chain.

        The tree is a decision tree over category properties: each level
        splits the candidate space, so a match on a chain segment at depth
        ``d`` pins down a subset of roughly ``catalog / 2**d`` products. The
        information gain of that match is therefore
        ``log2(catalog_size / subtree_size)`` — deeper (smaller) subtrees
        carry exponentially more bits, which is exactly the binary-search
        intuition. We sum the gain over every chain segment whose property
        shares a token with ``tokens``.

        Unlike a raw ``depth`` term, the gain is invariant to how long the
        root path is: two products whose chains reach the same node earn the
        same contribution regardless of breadcrumb depth above it.

        Returns 0.0 for products without a chain (unindexed products get a
        neutral score rather than being penalized)."""
        chain = self._asin_chain.get(asin)
        if not chain:
            return 0.0
        catalog_n = self.root.subtree_size()
        if catalog_n < 1:
            return 0.0
        bonus = 0.0
        node = self.root
        for segment in chain:
            child = node.children.get(segment)
            if child is None:
                break
            node = child
            seg_tokens = _segment_token_cache.get(segment)
            if seg_tokens is None:
                seg_tokens = frozenset(
                    token for token in segment.lower().replace("&", " ").split()
                )
                _segment_token_cache[segment] = seg_tokens
            if seg_tokens & tokens:
                size = node.subtree_size()
                if size > 0:
                    # information gain of a match at this depth: a smaller
                    # subtree pins down exponentially more bits (binary search)
                    bonus += math.log2(max(1.0, catalog_n / size))
        return bonus

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

    def converged_pool(self, keywords: list[str], pool: set[str],
                       threshold: int = 10) -> tuple[bool, set[str]]:
        """Tree-convergence gate for the LLM-vs-tree decision.

        Returns ``(converged, tree_pool)``. ``converged`` is True when the
        tree alone pins the candidates: at least one keyword resolved to a
        subtree, the conjunctive intersection of *all* tree-resolvable
        keywords (restricted to the caller's pool) is non-empty and at most
        ``threshold`` products. Keywords the tree cannot resolve (materials,
        colors, free words) are ignored — handled by the deterministic
        routes already. Implemented by checking each pool product's own
        chain against the keyword variants, so it costs O(pool × chain
        length) — no full-subtree expansion.
        """
        # build the set of tree-resolvable keyword variants once
        resolvable: set[str] = set()
        for keyword in keywords:
            resolvable |= self._variants(keyword)
        # split every chain segment into its tokens so a keyword matches
        # compound segments ("scarf" in "Fashion Scarves & Wraps")
        resolvable_tokens: set[str] = set()
        for variant in resolvable:
            resolvable_tokens.add(variant)
        for variant in resolvable:
            for token in variant.split():
                token = self._normalize_token(token)
                if token:
                    resolvable_tokens.add(token)
        tree_pool: set[str] = set()
        for asin in pool:
            chain = self.chain(asin)
            # product matches when ANY chain segment has a token shared with
            # the resolved keyword variants (inner any scans segment tokens)
            hit = any(
                any(self._normalize_token(seg_token) in resolvable_tokens
                    for seg_token in seg.split())
                for seg in chain
            )
            if hit:
                tree_pool.add(asin)
        if not tree_pool:
            return False, set()
        return len(tree_pool) <= threshold, tree_pool

    # ------------------------------------------------------------------ stats
    @property
    def node_count(self) -> int:
        """Total nodes in the tree, including the synthetic root."""
        return len(self._chain_to_node) + 1  # + root

    @property
    def leaf_count(self) -> int:
        """Number of leaf nodes (nodes with no children)."""
        return sum(1 for n in self._chain_to_node.values() if n.is_leaf())

    def depth_histogram(self) -> dict[int, int]:
        """Count of nodes at each depth, keyed by depth (sorted ascending)."""
        hist: dict[int, int] = {}
        # tally nodes per depth; sorting yields a stable depth profile
        for node in self._chain_to_node.values():
            hist[node.depth] = hist.get(node.depth, 0) + 1
        return dict(sorted(hist.items()))

    def families(self, min_size: int = 2) -> list[tuple[list[str], int]]:
        """Chains shared by >= min_size products (the ambiguous families).

        Returns ``(chain, product_count)`` pairs sorted by count descending,
        so the most ambiguous families (largest shared chains) come first.
        """
        return sorted(
            ((list(chain), len(node.products)) for chain, node in
             self._chain_to_node.items() if len(node.products) >= min_size),
            key=lambda item: -item[1],  # negative count -> descending order
        )

    # ------------------------------------------------------------------ iter
    def iter_nodes(self) -> Iterator[_Node]:
        """Yield every node in the tree via iterative depth-first traversal.

        Uses an explicit stack (rather than recursion) to avoid hitting the
        interpreter recursion limit on deep category paths.
        """
        stack = [self.root]
        while stack:
            node = stack.pop()
            yield node
            stack.extend(node.children.values())  # push children for DFS

    def to_dict(self, node: _Node | None = None, limit: int | None = None) -> dict:
        """Serializable tree for the demo UI.

        Recursively renders a node as a plain dict. ``limit`` bounds children
        per node so a huge tree stays renderable; leaf nodes expose at most 10
        sample products to keep the payload small.
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
            children = children[:limit]  # cap fan-out so wide trees stay small
        if children:
            # recurse into (capped) children; non-leaf nodes show structure
            out["children"] = [self.to_dict(c, limit) for c in children]
        elif node.products:
            out["products"] = node.products[:10]  # leaf: show a sample, not all
        return out
