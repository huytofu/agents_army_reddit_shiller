"""Thin post drafting agent for X timeline posts."""

from __future__ import annotations

import json
import re

from x_manager.config import SPECIALIST_LLM_CONFIG
from x_manager.prompts import load_shared_guidelines
from x_manager.schemas import DraftContent, IdentityCard
from x_manager.services.llm_client import XLlmClient

POST_SYSTEM_PROMPT = """You write original X (Twitter) posts as the given identity.

Return ONLY valid JSON:
{"body": "post text", "hashtags": ["optional", "tags"]}

Rules:
- Posts are rare. Draft when instructions say an original timeline post is natural.
- promote is always true for posts — include a natural Entourage app/blog mention.
- Soften tone: personal story first, soft mention second — never ad copy or link dumps.
- Include 1–2 relevant hashtags from the identity list when natural (no hashtag stuffing).
- Keep within X length; genuine_reply does NOT apply to posts.
"""


def _build_post_instructions(*, promote_target: str, supervisor_instructions: str) -> str:
    parts: list[str] = []
    if supervisor_instructions.strip():
        parts.append(supervisor_instructions.strip())
    target_label = "Entourage app" if promote_target == "app" else "Entourage blog"
    parts.append(
        f"Post must promote ({target_label}) — soften delivery: lead with genuine value or story, "
        "then one subtle mention; never sound like an ad campaign. Use 1–2 hashtags max."
    )
    return " ".join(parts)


def _append_hashtags(body: str, tags: list[str], allowed: list[str]) -> tuple[str, list[str]]:
    normalized_allowed = {t.lower().lstrip("#"): t.lstrip("#") for t in allowed}
    chosen: list[str] = []
    for tag in tags:
        key = tag.lower().lstrip("#")
        if key in normalized_allowed and key not in {c.lower() for c in chosen}:
            chosen.append(normalized_allowed[key])
        if len(chosen) >= 2:
            break
    if not chosen and allowed:
        chosen = [allowed[0].lstrip("#")]
    existing = body.lower()
    extras = [f"#{t}" for t in chosen if f"#{t.lower()}" not in existing]
    if extras:
        body = f"{body.rstrip()} {' '.join(extras)}".strip()
    return body, chosen


class PostAgent:
    def __init__(self, llm_client: XLlmClient | None = None):
        self.llm_client = llm_client or XLlmClient(config=SPECIALIST_LLM_CONFIG)

    async def draft(
        self,
        identity: IdentityCard,
        *,
        promote: bool,
        promote_target: str,
        specialist_instructions: str,
    ) -> DraftContent:
        instructions = _build_post_instructions(
            promote_target=promote_target,
            supervisor_instructions=specialist_instructions,
        )
        user_payload = {
            "hashtags_available": identity.hashtags,
            "promote": True,
            "promote_target": promote_target,
            "genuine_reply": False,
            "specialist_instructions": instructions,
        }
        messages = [
            {
                "role": "system",
                "content": "\n\n".join(
                    part
                    for part in [
                        POST_SYSTEM_PROMPT,
                        load_shared_guidelines(),
                        identity.system_prompt,
                    ]
                    if part
                ),
            },
            {"role": "user", "content": json.dumps(user_payload, indent=2)},
        ]
        raw = await self.llm_client.chat_completion(messages)
        parsed = _parse_json(raw)
        body = str(parsed.get("body", "")).strip()
        raw_tags = parsed.get("hashtags") or []
        if isinstance(raw_tags, str):
            raw_tags = [raw_tags]
        body, tags = _append_hashtags(body, [str(t) for t in raw_tags], identity.hashtags)
        return DraftContent(
            kind="post",
            body=body,
            promote=True,
            promote_target=promote_target if promote else "app",  # type: ignore[arg-type]
            genuine_reply=False,
            hashtags=tags,
        )


def _parse_json(raw: str) -> dict:
    text = raw.strip()
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fence:
        text = fence.group(1)
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        text = text[start : end + 1]
    return json.loads(text)
