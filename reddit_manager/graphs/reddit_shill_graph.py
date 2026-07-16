"""LangGraph wiring for Reddit shill workflow."""

from __future__ import annotations

import json
import logging
import random
from dataclasses import replace
from pathlib import Path
from typing import Any

from reddit_manager.agents import CommentAgent, PostAgent, RedditPipelineAgent
from reddit_manager.agents.reddit_pipeline_agent import resolve_promote_target
from reddit_manager.config import QUOTA_CONFIG, REDDIT_CONFIG, WORKER_CONFIG
from reddit_manager.schemas import (
    ActionLogEntry,
    RedditGraphState,
    RedditPipelineDecision,
    utc_now_iso,
)
from reddit_manager.services.humanization import (
    human_wait,
    sample_posts_per_browse,
    should_allow_post,
    should_genuine_reply,
)
from reddit_manager.services.praw_client import RedditClient
from reddit_manager.services.quota_store import QuotaStore
from reddit_manager.services.target_picker import pick_comment_target

try:
    from langgraph.graph import END, StateGraph  # type: ignore[import-not-found]
except Exception:  # pragma: no cover
    END = "__end__"
    StateGraph = None

logger = logging.getLogger(__name__)


class RedditGraphError(RuntimeError):
    pass


class RedditShillWorkflow:
    def __init__(
        self,
        *,
        reddit_client: RedditClient,
        quota_store: QuotaStore,
        pipeline_agent: RedditPipelineAgent | None = None,
        comment_agent: CommentAgent | None = None,
        post_agent: PostAgent | None = None,
        config: dict[str, Any] | None = None,
    ):
        self.reddit_client = reddit_client
        self.quota_store = quota_store
        self.pipeline_agent = pipeline_agent or RedditPipelineAgent()
        self.comment_agent = comment_agent or CommentAgent()
        self.post_agent = post_agent or PostAgent()
        self.config = config or WORKER_CONFIG

    async def main_think(self, state: RedditGraphState) -> RedditGraphState:
        if _rounds_exhausted(state, self.config):
            return _with_decision(state, _done_decision("Main agent round limit reached."))

        snapshot_state = replace(
            state,
            quota_snapshot=self.quota_store.get_snapshot(state.identity.id) if state.identity else {},
        )
        try:
            decision = await self.pipeline_agent.think(snapshot_state)
        except Exception as exc:
            return _append_error(state, f"Supervisor failed: {exc}")

        decision = _enforce_invariants(decision, snapshot_state, self.quota_store)
        return _with_decision(replace(state, main_round=state.main_round + 1), decision)

    async def browse(self, state: RedditGraphState) -> RedditGraphState:
        if state.identity is None:
            return _append_error(state, "Missing identity for browse.")

        decision = state.main_decision
        subreddit = _pick_subreddit(state, decision.subreddit if decision else "")
        sort = decision.sort if decision else "hot"
        limit = sample_posts_per_browse()
        items = self.reddit_client.browse_subreddit(subreddit, sort=sort, limit=limit)
        self.quota_store.remember_subreddit(state.identity.id, subreddit)

        log = [
            *state.action_log,
            ActionLogEntry(
                timestamp=utc_now_iso(),
                action="browse",
                details={"subreddit": subreddit, "sort": sort, "count": len(items)},
            ),
        ]
        return replace(
            state,
            browse_satisfied=len(items) > 0,
            browse_context=[*state.browse_context, *items][-24:],
            action_log=log,
        )

    async def wait_after_browse(self, state: RedditGraphState) -> RedditGraphState:
        seconds = await human_wait(fast=state.fast)
        log = [
            *state.action_log,
            ActionLogEntry(
                timestamp=utc_now_iso(),
                action="wait_after_browse",
                details={"seconds": seconds},
            ),
        ]
        return replace(state, action_log=log)

    async def wait_before_apply(self, state: RedditGraphState) -> RedditGraphState:
        seconds = await human_wait(fast=state.fast)
        log = [
            *state.action_log,
            ActionLogEntry(
                timestamp=utc_now_iso(),
                action="wait_before_apply",
                details={"seconds": seconds},
            ),
        ]
        return replace(state, action_log=log)

    async def skip_flip(self, state: RedditGraphState) -> RedditGraphState:
        if state.skip_after_browse:
            log = [
                *state.action_log,
                ActionLogEntry(
                    timestamp=utc_now_iso(),
                    action="skip_forced",
                    details={"reason": "p_skip coin flip"},
                ),
            ]
            return _with_decision(replace(state, action_log=log), _done_decision("Browse-only skip."))
        return state

    async def pick_target(self, state: RedditGraphState) -> RedditGraphState:
        target = pick_comment_target(state.browse_context)
        if target is None:
            return _append_error(state, "No comment target available.")
        genuine = should_genuine_reply()
        log = [
            *state.action_log,
            ActionLogEntry(
                timestamp=utc_now_iso(),
                action="target_picked",
                details={"post_id": target.post_id, "genuine_reply": genuine},
            ),
        ]
        return replace(state, selected_target=target, genuine_reply=genuine, action_log=log)

    async def generate_comment(self, state: RedditGraphState) -> RedditGraphState:
        if state.identity is None or state.selected_target is None:
            return _append_error(state, "Missing identity or target for comment.")

        decision = state.main_decision or RedditPipelineDecision(decision="comment")
        promote = decision.promote and not state.genuine_reply
        promote_target = resolve_promote_target(
            state.identity,
            promote=promote,
            decision_target=decision.promote_target,
        )

        try:
            draft = await self.comment_agent.draft(
                state.identity,
                state.selected_target,
                promote=promote,
                promote_target=promote_target,
                genuine_reply=state.genuine_reply,
                specialist_instructions=decision.specialist_instructions,
            )
        except Exception as exc:
            return _append_error(state, f"Comment draft failed: {exc}")

        return replace(state, pending_draft=draft)

    async def generate_post(self, state: RedditGraphState) -> RedditGraphState:
        if state.identity is None:
            return _append_error(state, "Missing identity for post.")

        decision = _apply_post_promotion_defaults(
            state.main_decision or RedditPipelineDecision(decision="post"),
            state,
        )
        subreddit = _pick_subreddit(state, decision.subreddit)
        try:
            draft = await self.post_agent.draft(
                state.identity,
                subreddit=subreddit,
                promote=True,
                promote_target=decision.promote_target,
                specialist_instructions=decision.specialist_instructions,
            )
        except Exception as exc:
            return _append_error(state, f"Post draft failed: {exc}")

        return replace(state, pending_draft=draft, main_decision=decision)

    async def apply_action(self, state: RedditGraphState) -> RedditGraphState:
        draft = state.pending_draft
        if draft is None or state.identity is None:
            return state

        result: dict[str, Any] = {"dry_run": not state.live}
        comments_this_run = state.comments_this_run
        posts_this_run = state.posts_this_run

        if draft.kind == "comment" and state.selected_target is not None:
            if state.live:
                try:
                    result = self.reddit_client.submit_comment(state.selected_target.post_id, draft.body)
                except Exception as exc:
                    self.quota_store.set_cooldown(
                        state.identity.id,
                        float(QUOTA_CONFIG["RATE_LIMIT_COOLDOWN_HOURS"]),
                    )
                    return _append_error(state, f"Comment submit failed: {exc}")
            self.quota_store.record_comment(state.identity.id)
            comments_this_run += 1
        elif draft.kind == "post" and draft.subreddit and draft.title:
            if state.live:
                try:
                    result = self.reddit_client.submit_post(draft.subreddit, draft.title, draft.body)
                except Exception as exc:
                    self.quota_store.set_cooldown(
                        state.identity.id,
                        float(QUOTA_CONFIG["RATE_LIMIT_COOLDOWN_HOURS"]),
                    )
                    return _append_error(state, f"Post submit failed: {exc}")
            self.quota_store.record_post(state.identity.id)
            posts_this_run += 1
        else:
            return _append_error(state, "Invalid draft for apply_action.")

        if draft.promote and "entourage" in draft.body.lower():
            self.quota_store.record_link(state.identity.id)

        artifact_path = _write_artifact(state, draft, result)
        log = [
            *state.action_log,
            ActionLogEntry(
                timestamp=utc_now_iso(),
                action="apply",
                details={"kind": draft.kind, "artifact": str(artifact_path), "result": result},
            ),
        ]

        if draft.kind == "comment":
            return replace(
                state,
                pending_draft=None,
                comments_this_run=comments_this_run,
                action_log=log,
            )
        return replace(
            state,
            pending_draft=None,
            posts_this_run=posts_this_run,
            action_log=log,
        )


def build_reddit_shill_graph(workflow: RedditShillWorkflow):
    if StateGraph is None:
        raise RedditGraphError("langgraph is required to build the Reddit shill graph.")

    graph = StateGraph(RedditGraphState)
    graph.add_node("main_think", workflow.main_think)
    graph.add_node("browse", workflow.browse)
    graph.add_node("wait_after_browse", workflow.wait_after_browse)
    graph.add_node("wait_before_apply", workflow.wait_before_apply)
    graph.add_node("skip_flip", workflow.skip_flip)
    graph.add_node("pick_target", workflow.pick_target)
    graph.add_node("generate_comment", workflow.generate_comment)
    graph.add_node("generate_post", workflow.generate_post)
    graph.add_node("apply_action", workflow.apply_action)

    graph.set_entry_point("main_think")
    graph.add_conditional_edges("main_think", _route_from_think, {
        "browse": "browse",
        "comment": "pick_target",
        "post": "generate_post",
        "skip": END,
        "done": END,
    })
    graph.add_edge("browse", "wait_after_browse")
    graph.add_edge("wait_after_browse", "skip_flip")
    graph.add_conditional_edges("skip_flip", _route_after_skip, {
        "done": END,
        "continue": "main_think",
    })
    graph.add_edge("pick_target", "generate_comment")
    graph.add_edge("generate_comment", "wait_before_apply")
    graph.add_edge("generate_post", "wait_before_apply")
    graph.add_edge("wait_before_apply", "apply_action")
    graph.add_edge("apply_action", "main_think")

    return graph.compile()


def initial_state(**kwargs) -> RedditGraphState:
    return RedditGraphState(**kwargs)


def _route_from_think(state: RedditGraphState) -> str:
    decision = state.main_decision.decision if state.main_decision else "done"
    if decision in {"comment", "post"} and not state.browse_satisfied:
        return "browse"
    if decision == "comment" and state.comments_this_run >= QUOTA_CONFIG["MAX_COMMENTS_PER_RUN"]:
        return "done"
    if decision == "post" and state.posts_this_run >= QUOTA_CONFIG["MAX_POSTS_PER_RUN"]:
        return "done"
    return decision


def _route_after_skip(state: RedditGraphState) -> str:
    if state.main_decision and state.main_decision.decision == "done":
        return "done"
    if state.skip_after_browse:
        return "done"
    return "continue"


def _rounds_exhausted(state: RedditGraphState, config: dict[str, Any]) -> bool:
    return state.main_round >= int(config["MAIN_AGENT_MAX_ROUNDS"])


def _with_decision(state: RedditGraphState, decision: RedditPipelineDecision) -> RedditGraphState:
    return replace(state, main_decision=decision)


def _done_decision(reason: str) -> RedditPipelineDecision:
    return RedditPipelineDecision(decision="done", reason=reason)


def _append_error(state: RedditGraphState, message: str) -> RedditGraphState:
    return replace(state, errors=[*state.errors, message])


def _enforce_invariants(
    decision: RedditPipelineDecision,
    state: RedditGraphState,
    quota_store: QuotaStore,
) -> RedditPipelineDecision:
    identity_id = state.identity.id if state.identity else ""

    if decision.decision == "post":
        ok, reason = quota_store.can_post(identity_id)
        if not ok:
            logger.info("Post decision overridden (%s); preferring comment or done.", reason)
            ok_comment, _ = quota_store.can_comment(identity_id)
            if ok_comment and state.browse_satisfied:
                return replace(
                    decision,
                    decision="comment",
                    promote=True,
                    reason=f"Post blocked by quota ({reason}); falling back to comment.",
                )
            return _done_decision(f"Post blocked: {reason}")

        if not should_allow_post():
            logger.info("Post decision overridden by P_ALLOW_POST ratio gate; preferring comment.")
            ok_comment, _ = quota_store.can_comment(identity_id)
            if (
                ok_comment
                and state.browse_satisfied
                and state.comments_this_run < QUOTA_CONFIG["MAX_COMMENTS_PER_RUN"]
            ):
                return replace(
                    decision,
                    decision="comment",
                    promote=True,
                    promote_target=resolve_promote_target(
                        state.identity,
                        promote=True,
                        decision_target=decision.promote_target,
                    ),
                    reason="Post ratio gate → comment (comments favored over posts).",
                )
            return _done_decision("Post ratio gate; no comment slot available.")

        return _apply_post_promotion_defaults(decision, state)

    if decision.decision == "comment":
        ok, reason = quota_store.can_comment(identity_id)
        if not ok:
            return _done_decision(f"Comment blocked: {reason}")

    if decision.decision in {"comment", "post"} and not state.browse_satisfied:
        return replace(decision, decision="browse", reason="Must browse before writing.")

    return decision


def _apply_post_promotion_defaults(
    decision: RedditPipelineDecision,
    state: RedditGraphState,
) -> RedditPipelineDecision:
    """Posts always promote; promote_target uses same rule as comments."""
    target = resolve_promote_target(
        state.identity,
        promote=True,
        decision_target=decision.promote_target,
    )
    return replace(
        decision,
        promote=True,
        promote_target=target,  # type: ignore[arg-type]
    )


def _pick_subreddit(state: RedditGraphState, requested: str) -> str:
    if state.identity is None:
        return requested or random.choice(REDDIT_CONFIG["DEFAULT_SUBREDDITS"])

    allowlist = set(REDDIT_CONFIG["DEFAULT_SUBREDDITS"])
    preferred = [s for s in state.identity.preferred_subreddits if s in allowlist or s]
    if not preferred:
        preferred = list(REDDIT_CONFIG["DEFAULT_SUBREDDITS"])

    recent = set(state.quota_snapshot.get("identity", {}).get("last_subreddits", []))
    candidates = [s for s in preferred if s not in recent] or preferred
    if requested and requested in candidates:
        return requested
    return random.choice(candidates)


def _write_artifact(state: RedditGraphState, draft, result: dict[str, Any]) -> Path:
    root = Path(state.artifacts_dir or WORKER_CONFIG["ARTIFACTS_ROOT"])
    root.mkdir(parents=True, exist_ok=True)
    path = root / f"{draft.kind}_{len(state.action_log)}.json"
    path.write_text(
        json.dumps(
            {
                "draft": draft.__dict__,
                "result": result,
                "identity": state.identity.id if state.identity else "",
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return path
