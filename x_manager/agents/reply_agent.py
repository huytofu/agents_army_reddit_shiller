"""Thin reply drafting agent for X."""

from __future__ import annotations

import json
import re

from x_manager.config import SPECIALIST_LLM_CONFIG
from x_manager.prompts import load_shared_guidelines
from x_manager.schemas import DraftContent, IdentityCard, SelectedTarget
from x_manager.services.llm_client import XLlmClient

REPLY_SYSTEM_PROMPT = """You write X (Twitter) replies as the given identity.

Return ONLY valid JSON:
{"body": "reply text"}

Rules:
- Sound human and specific to the parent tweet.
- Follow shared guidelines and specialist instructions exactly.
- Keep replies concise (X length). Avoid hashtag spam in replies — zero or at most one tag only if natural.
- If genuine_reply=true: NO app/blog mentions and NO links — helpful or lightly funny only.
- If promote=true and genuine_reply=false: soft mention only — one subtle personal-experience reference max.
- When in doubt on promote=true, prefer helpful reply with zero promo.
"""


def _build_specialist_instructions(
    *,
    promote: bool,
    promote_target: str,
    genuine_reply: bool,
    supervisor_instructions: str,
) -> str:
    parts: list[str] = []
    if supervisor_instructions.strip():
        parts.append(supervisor_instructions.strip())

    if genuine_reply:
        parts.append(
            "Humanization gate active: write a genuinely helpful reply with zero product/blog mentions and no links."
        )
    elif promote:
        target_label = "Entourage app" if promote_target == "app" else "Entourage blog"
        parts.append(
            f"Supervisor requested soft {target_label} mention — dial down: at most one subtle personal aside, "
            "only if it fits naturally after giving real value; skip the mention entirely if it would feel salesy."
        )
    else:
        parts.append("No promotion requested — focus on being helpful.")

    return " ".join(parts)


class ReplyAgent:
    def __init__(self, llm_client: XLlmClient | None = None):
        self.llm_client = llm_client or XLlmClient(config=SPECIALIST_LLM_CONFIG)

    async def draft(
        self,
        identity: IdentityCard,
        target: SelectedTarget,
        *,
        promote: bool,
        promote_target: str,
        genuine_reply: bool,
        specialist_instructions: str,
    ) -> DraftContent:
        effective_promote = promote and not genuine_reply
        instructions = _build_specialist_instructions(
            promote=effective_promote,
            promote_target=promote_target,
            genuine_reply=genuine_reply,
            supervisor_instructions=specialist_instructions,
        )
        user_payload = {
            "target": {
                "tweet_id": target.tweet_id,
                "author_username": target.author_username,
                "text": target.text,
                "like_count": target.like_count,
                "query": target.query,
            },
            "promote": effective_promote,
            "promote_target": promote_target if effective_promote else "none",
            "genuine_reply": genuine_reply,
            "specialist_instructions": instructions,
        }
        messages = [
            {
                "role": "system",
                "content": "\n\n".join(
                    part
                    for part in [
                        REPLY_SYSTEM_PROMPT,
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
        actually_promoted = effective_promote and _body_mentions_entourage(body)
        return DraftContent(
            kind="reply",
            body=body,
            promote=actually_promoted,
            promote_target=promote_target if actually_promoted else "none",  # type: ignore[arg-type]
            genuine_reply=genuine_reply,
        )


# Back-compat alias
CommentAgent = ReplyAgent


def _body_mentions_entourage(body: str) -> bool:
    lowered = body.lower()
    return "entourage" in lowered or "entourage-ai.life" in lowered


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
