"""Optional LLM reranker (OpenAI-compatible chat completions, stdlib only).

Configured exclusively through environment variables:

    TECHJAM_LLM_API_BASE  e.g. https://api.openai.com/v1
    TECHJAM_LLM_API_KEY   the API key (never committed)
    TECHJAM_LLM_MODEL     e.g. gpt-4o-mini (default)

When no key is configured the agent runs fully offline with the deterministic
heuristic ranking — the LLM is a soft rerank of the top candidates and any
failure/timeout silently falls back to the heuristic order.
"""
from __future__ import annotations

import json
import os
import re
import urllib.request
from pathlib import Path

# Network timeout for a rerank request. Bounded so a hung provider can never
# stall the offline-first agent; the ping probe below uses a tighter 8s timeout.
TIMEOUT_SECONDS = 25.0


class LLMReranker:
    """Optional soft reranker over the top retrieval candidates.

    Wraps an OpenAI-compatible ``/chat/completions`` endpoint and asks the model
    to order ASINs from best to worst fit. It is intentionally best-effort: when
    no credentials are configured, or any call fails/times out, callers fall back
    to the deterministic heuristic order, so the agent never depends on network
    or LLM availability.
    """

    def __init__(self, api_base: str, api_key: str, model: str) -> None:
        """Store the endpoint config, normalizing the base URL.

        Args:
            api_base: Root URL of an OpenAI-compatible API (e.g.
                ``https://api.openai.com/v1``); trailing slashes are stripped so
                the ``/chat/completions`` path appends cleanly.
            api_key: Bearer token sent in the ``Authorization`` header. Held in
                memory only and never logged or returned by this class.
            model: Model identifier placed in each request body.

        Side effects:
            None — this only records configuration on the instance.
        """
        self.api_base = api_base.rstrip("/")
        self.api_key = api_key
        self.model = model

    @classmethod
    def from_env(cls) -> "LLMReranker | None":
        """Build a reranker from the ``TECHJAM_LLM_*`` environment variables.

        Reads the official env-only configuration (base URL, key, model) and
        returns an instance, or ``None`` when the base URL or key is missing.
        The ``None`` result is the signal to callers to stay fully offline with
        the deterministic heuristic ranking. ``TECHJAM_LLM_MODEL`` is optional
        and defaults to ``gpt-4o-mini``.
        """
        api_base = os.environ.get("TECHJAM_LLM_API_BASE")
        api_key = os.environ.get("TECHJAM_LLM_API_KEY")
        model = os.environ.get("TECHJAM_LLM_MODEL", "gpt-4o-mini")
        if not api_base or not api_key:
            return None
        return cls(api_base, api_key, model)

    @classmethod
    def from_local_defaults(cls) -> "LLMReranker | None":
        """Build a reranker from this machine's DeepSeek credentials.

        Reads ``DEEPSEEK_API_KEY`` from the environment, or falls back to the
        harness credentials file at ``~/.dsh/.credentials.yaml`` (parsed with a
        regex, no YAML dependency). Returns ``None`` when no key is found so the
        agent can continue offline. The key is never logged or returned.

        Failure modes:
            A missing/unreadable credentials file, or a file without a
            ``DEEPSEEK_API_KEY:`` entry, yields ``None`` rather than raising.
        """
        import re

        api_key = os.environ.get("DEEPSEEK_API_KEY")
        if not api_key:
            try:
                creds = Path(os.path.expanduser("~/.dsh/.credentials.yaml")).read_text()
                # Capture the first non-whitespace token after "DEEPSEEK_API_KEY:".
                match = re.search(r"DEEPSEEK_API_KEY:\s*(\S+)", creds)
                api_key = match.group(1) if match else None
            except Exception:
                # Any read/parse error degrades to "no credentials", not a crash.
                api_key = None
        if not api_key:
            return None
        return cls("https://api.deepseek.com/v1", api_key,
                   os.environ.get("DEEPSEEK_MODEL", "deepseek-v4-flash"))

    def ping(self) -> bool:
        """Cheap liveness probe: is the configured model actually reachable?

        Sends a minimal one-token completion request and reports whether the
        endpoint answers with HTTP 200. Used to decide whether the LLM rerank
        route is worth enabling for a session.

        Failure modes:
            Any network, timeout, auth, or protocol error returns ``False``;
            this method never raises.
        """
        # One-token prompt keeps the probe cheap and avoids burning quota.
        body = {"model": self.model,
                "messages": [{"role": "user", "content": "ping"}],
                "max_tokens": 1}
        request = urllib.request.Request(
            f"{self.api_base}/chat/completions",
            data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json",
                     "Authorization": f"Bearer {self.api_key}"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=8) as response:
                return response.status == 200
        except Exception:
            # Any failure means "unreachable"; let the caller fall back offline.
            return False

    def rerank(self, conversation: str, candidates: list[dict]) -> tuple[list[str] | None, dict]:
        """Rerank candidate products with the LLM and return an ASIN order.

        Args:
            conversation: The full customer conversation text used as ranking
                context (constraints in the text must be respected).
            candidates: Candidate product dicts in their current (heuristic)
                order. Each dict must expose ``parent_asin`` and may expose
                ``title``, ``categories``, and ``features``.

        Returns:
            A tuple ``(ordered_asins, usage)``. ``ordered_asins`` is a list of
            every candidate ASIN ordered best-first by the model (with any
            missing/invalid ASINs appended to preserve completeness), or
            ``None`` when the request itself failed. ``usage`` is a
            ``{"prompt_tokens", "completion_tokens"}`` dict, zeroed on failure.

        Contract / failure modes:
            - Any network/timeout/decode error returns ``(None, zeroed usage)``
              so the caller keeps the heuristic order.
            - A malformed model reply still yields a best-effort order: it
              parses the first JSON array, then falls back to scanning for ASIN
              tokens after ``"ranking"``, and finally appends every candidate
              that the model omitted, so the result is always a complete list
              when the request itself succeeded.
        """
        # Render candidates as a compact numbered list for the prompt, truncating
        # feature bullets to 3 to keep the prompt short enough for small models.
        catalog_block = "\n".join(
            f"{index}. {item['parent_asin']}: {item.get('title', '')} "
            f"| categories: {', '.join(item.get('categories', []))} "
            f"| features: {'; '.join((item.get('features') or [])[:3])}"
            for index, item in enumerate(candidates, start=1)
        )
        # Prompt contract: the model must emit a single JSON object listing every
        # ASIN; explicit "no markdown / no explanation" keeps the reply parseable.
        prompt = (
            "You are the ranking stage of an e-commerce shopping assistant. "
            "Rank the following catalog products from best to worst fit for "
            "this customer conversation. Respect hard constraints strictly. "
            "Output STRICTLY a JSON object {\"ranking\": [\"ASIN1\", \"ASIN2\", ...]} "
            "containing every listed ASIN. No markdown, no explanation, nothing else.\n\n"
            f"Customer conversation:\n{conversation}\n\n"
            f"Candidate products:\n{catalog_block}"
        )
        # temperature=0.0 makes ranking deterministic; max_tokens=900 is enough
        # for a full ranking of the typical top-k candidate pool.
        body = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": "You return JSON only."},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.0,
            "max_tokens": 900,
        }
        request = urllib.request.Request(
            f"{self.api_base}/chat/completions",
            data=json.dumps(body).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except Exception:
            # Transport/HTTP/JSON failure: bail out with a zeroed usage map so
            # the caller keeps the deterministic heuristic order untouched.
            return None, {"prompt_tokens": 0, "completion_tokens": 0}
        content = payload["choices"][0]["message"]["content"]
        usage = payload.get("usage") or {"prompt_tokens": 0, "completion_tokens": 0}
        # Whitelist of ASINs the model is allowed to return; anything else is
        # filtered out during ordering so the result stays within the candidate set.
        valid = {item["parent_asin"] for item in candidates}
        ranking: list[str] = []
        # Stage 1: prefer the strict JSON array the prompt asked for — the first
        # "[...]" in the reply. Wrapped in try/except because the model may emit
        # non-JSON text, in which case we move to the fallback below.
        match = re.search(r"\[[^\]]*\]", content)
        if match:
            try:
                ranking = [str(asin).strip() for asin in json.loads(match.group(0))]
            except Exception:
                ranking = []
        # Stage 2: truncated-output fallback. If the JSON parse produced nothing
        # (e.g. the reply was cut off), grab everything after '"ranking"[' and
        # scan for ASIN-shaped tokens; dict.fromkeys dedupes while preserving
        # the model's stated order.
        if not ranking:
            tail = re.split(r'"ranking"\s*:\s*\[', content, maxsplit=1)[-1]
            ranking = list(dict.fromkeys(re.findall(r"(B[0-9A-Z]{9})", tail)))
        # Keep only ASINs that actually appear in the candidate set, preserving
        # the model's order and dropping any hallucinated/foreign ASINs.
        ordered = [asin for asin in ranking if asin in valid]
        # Append any candidate the model omitted so the result is a complete,
        # non-duplicate ordering of every input candidate.
        ordered += [item["parent_asin"] for item in candidates if item["parent_asin"] not in ordered]
        return ordered, {
            "prompt_tokens": int(usage.get("prompt_tokens") or 0),
            "completion_tokens": int(usage.get("completion_tokens") or 0),
        }
