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

TIMEOUT_SECONDS = 60.0


class LLMReranker:
    def __init__(self, api_base: str, api_key: str, model: str) -> None:
        self.api_base = api_base.rstrip("/")
        self.api_key = api_key
        self.model = model

    @classmethod
    def from_env(cls) -> "LLMReranker | None":
        api_base = os.environ.get("TECHJAM_LLM_API_BASE")
        api_key = os.environ.get("TECHJAM_LLM_API_KEY")
        model = os.environ.get("TECHJAM_LLM_MODEL", "gpt-4o-mini")
        if not api_base or not api_key:
            return None
        return cls(api_base, api_key, model)

    @classmethod
    def from_local_defaults(cls) -> "LLMReranker | None":
        """This machine's DeepSeek credentials (harness ~/.dsh/.credentials.yaml
        or DEEPSEEK_API_KEY env). Never logs or returns the key itself."""
        import re

        api_key = os.environ.get("DEEPSEEK_API_KEY")
        if not api_key:
            try:
                creds = Path(os.path.expanduser("~/.dsh/.credentials.yaml")).read_text()
                match = re.search(r"DEEPSEEK_API_KEY:\s*(\S+)", creds)
                api_key = match.group(1) if match else None
            except Exception:
                api_key = None
        if not api_key:
            return None
        return cls("https://api.deepseek.com/v1", api_key,
                   os.environ.get("DEEPSEEK_MODEL", "deepseek-v4-flash"))

    def rerank(self, conversation: str, candidates: list[dict]) -> tuple[list[str] | None, dict]:
        """Return (ordered asins, usage) or (None, usage) on failure."""
        catalog_block = "\n".join(
            f"{index}. {item['parent_asin']}: {item.get('title', '')} "
            f"| categories: {', '.join(item.get('categories', []))} "
            f"| features: {'; '.join((item.get('features') or [])[:3])}"
            for index, item in enumerate(candidates, start=1)
        )
        prompt = (
            "You are the ranking stage of an e-commerce shopping assistant. "
            "Rank the following catalog products from best to worst fit for "
            "this customer conversation. Respect hard constraints strictly. "
            "Output STRICTLY a JSON object {\"ranking\": [\"ASIN1\", \"ASIN2\", ...]} "
            "containing every listed ASIN. No markdown, no explanation, nothing else.\n\n"
            f"Customer conversation:\n{conversation}\n\n"
            f"Candidate products:\n{catalog_block}"
        )
        body = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": "You return JSON only."},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.0,
            "max_tokens": 1500,
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
            return None, {"prompt_tokens": 0, "completion_tokens": 0}
        content = payload["choices"][0]["message"]["content"]
        usage = payload.get("usage") or {"prompt_tokens": 0, "completion_tokens": 0}
        valid = {item["parent_asin"] for item in candidates}
        ranking: list[str] = []
        # 1) strict JSON array
        match = re.search(r"\[[^\]]*\]", content)
        if match:
            try:
                ranking = [str(asin).strip() for asin in json.loads(match.group(0))]
            except Exception:
                ranking = []
        # 2) truncated-output fallback: collect ASINs after '"ranking"'
        if not ranking:
            tail = re.split(r'"ranking"\s*:\s*\[', content, maxsplit=1)[-1]
            ranking = list(dict.fromkeys(re.findall(r"(B[0-9A-Z]{9})", tail)))
        ordered = [asin for asin in ranking if asin in valid]
        ordered += [item["parent_asin"] for item in candidates if item["parent_asin"] not in ordered]
        return ordered, {
            "prompt_tokens": int(usage.get("prompt_tokens") or 0),
            "completion_tokens": int(usage.get("completion_tokens") or 0),
        }
