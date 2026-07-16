"""Thin post drafting agent."""

from __future__ import annotations

import json
import re

from reddit_manager.config import SPECIALIST_LLM_CONFIG
from reddit_manager.prompts import load_shared_guidelines
from reddit_manager.schemas import DraftContent, IdentityCard
from reddit_manager.services.llm_client import RedditLlmClient

POST_SYSTEM_PROMPT = """You write Reddit posts as the given identity.

Return ONLY valid JSON:
{"title": "post title", "body": "post body"}

Rules:
- Posts are rare. Draft when instructions say a new thread is natural.
- promote is always true for posts — include a natural Entourage app/blog mention.
- YOU soften tone: personal story first, soft mention second — never ad copy or link dumps.
- genuine_reply does NOT apply to posts; always keep a subtle product/blog reference when promote=true.
- Sound community-native, not like marketing.
"""


def _build_post_instructions(*, promote_target: str, supervisor_instructions: str) -> str:
    parts: list[str] = []
    if supervisor_instructions.strip():
        parts.append(supervisor_instructions.strip())
    target_label = "Entourage app" if promote_target == "app" else "Entourage blog"
    parts.append(
        f"Post must promote ({target_label}) — soften delivery: lead with genuine value or story, "
        "then one subtle mention; never sound like an ad campaign."
    )
    return " ".join(parts)


class PostAgent:
    def __init__(self, llm_client: RedditLlmClient | None = None):
        self.llm_client = llm_client or RedditLlmClient(config=SPECIALIST_LLM_CONFIG)

    async def draft(
        self,
        identity: IdentityCard,
        *,
        subreddit: str,
        promote: bool,
        promote_target: str,
        specialist_instructions: str,
    ) -> DraftContent:
        instructions = _build_post_instructions(
            promote_target=promote_target,
            supervisor_instructions=specialist_instructions,
        )
        user_payload = {
            "subreddit": subreddit,
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
        return DraftContent(
            kind="post",
            title=str(parsed.get("title", "")).strip(),
            body=body,
            subreddit=subreddit,
            promote=True,
            promote_target=promote_target if promote else "app",  # type: ignore[arg-type]
            genuine_reply=False,
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
