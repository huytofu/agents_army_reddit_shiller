"""LangGraph wiring for X shill workflow."""

from __future__ import annotations

import json
import logging
import random
from dataclasses import replace
from pathlib import Path
from typing import Any

from x_manager.agents import PostAgent, ReplyAgent, XPipelineAgent
from x_manager.agents.x_pipeline_agent import resolve_promote_target
from x_manager.config import QUOTA_CONFIG, WORKER_CONFIG, X_CONFIG
from x_manager.schemas import (
    ActionLogEntry,
    XGraphState,
    XPipelineDecision,
    utc_now_iso,
)
from x_manager.services.humanization import (
    human_wait,
    sample_posts_per_browse,
    should_allow_post,
    should_genuine_reply,
)
from x_manager.services.quota_store import QuotaStore
from x_manager.services.target_picker import pick_reply_target
from x_manager.services.x_client import XClient

try:
    from langgraph.graph import END, StateGraph  # type: ignore[import-not-found]
except Exception:  # pragma: no cover
    END = "__end__"
    StateGraph = None

logger = logging.getLogger(__name__)


class XGraphError(RuntimeError):
    pass


class XShillWorkflow:
    def __init__(
        self,
        *,
        x_client: XClient,
        quota_store: QuotaStore,
        pipeline_agent: XPipelineAgent | None = None,
        reply_agent: ReplyAgent | None = None,
        post_agent: PostAgent | None = None,
        config: dict[str, Any] | None = None,
    ):
        self.x_client = x_client
        self.quota_store = quota_store
        self.pipeline_agent = pipeline_agent or XPipelineAgent()
        self.reply_agent = reply_agent or ReplyAgent()
        self.post_agent = post_agent or PostAgent()
        self.config = config or WORKER_CONFIG

    async def main_think(self, state: XGraphState) -> XGraphState:
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

    async def browse(self, state: XGraphState) -> XGraphState:
        if state.identity is None:
            return _append_error(state, "Missing identity for browse.")

        decision = state.main_decision
        mode = "seeds" if decision and decision.decision == "browse_seeds" else (
            decision.browse_mode if decision else "search"
        )
        limit = sample_posts_per_browse()
        query = ""

        if mode == "seeds":
            seeds = state.identity.seed_accounts or []
            if not seeds:
                # Fall back to search if no seeds configured
                mode = "search"
            else:
                handle = random.choice(seeds)
                query = f"from:{handle}"
                items = self.x_client.get_user_timeline(handle, max_results=limit)
                self.quota_store.remember_query(state.identity.id, query)

        if mode != "seeds":
            query = _pick_search_query(state, decision.search_query if decision else "")
            items = self.x_client.search_recent(query, max_results=limit)
            self.quota_store.remember_query(state.identity.id, query)
            # If search empty and seeds exist, try one seed timeline
            if not items and state.identity.seed_accounts:
                handle = random.choice(state.identity.seed_accounts)
                query = f"from:{handle}"
                items = self.x_client.get_user_timeline(handle, max_results=limit)
                self.quota_store.remember_query(state.identity.id, query)

        log = [
            *state.action_log,
            ActionLogEntry(
                timestamp=utc_now_iso(),
                action="browse",
                details={"mode": mode, "query": query, "count": len(items)},
            ),
        ]
        return replace(
            state,
            browse_satisfied=len(items) > 0,
            browse_context=[*state.browse_context, *items][-24:],
            action_log=log,
        )

    async def wait_after_browse(self, state: XGraphState) -> XGraphState:
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

    async def wait_before_apply(self, state: XGraphState) -> XGraphState:
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

    async def skip_flip(self, state: XGraphState) -> XGraphState:
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

    async def pick_target(self, state: XGraphState) -> XGraphState:
        target = pick_reply_target(state.browse_context)
        if target is None:
            return _append_error(state, "No reply target available.")
        genuine = should_genuine_reply()
        log = [
            *state.action_log,
            ActionLogEntry(
                timestamp=utc_now_iso(),
                action="target_picked",
                details={"tweet_id": target.tweet_id, "genuine_reply": genuine},
            ),
        ]
        return replace(state, selected_target=target, genuine_reply=genuine, action_log=log)

    async def generate_reply(self, state: XGraphState) -> XGraphState:
        if state.identity is None or state.selected_target is None:
            return _append_error(state, "Missing identity or target for reply.")

        decision = state.main_decision or XPipelineDecision(decision="reply")
        promote = decision.promote and not state.genuine_reply
        promote_target = resolve_promote_target(
            state.identity,
            promote=promote,
            decision_target=decision.promote_target,
        )

        try:
            draft = await self.reply_agent.draft(
                state.identity,
                state.selected_target,
                promote=promote,
                promote_target=promote_target,
                genuine_reply=state.genuine_reply,
                specialist_instructions=decision.specialist_instructions,
            )
        except Exception as exc:
            return _append_error(state, f"Reply draft failed: {exc}")

        return replace(state, pending_draft=draft)

    async def generate_post(self, state: XGraphState) -> XGraphState:
        if state.identity is None:
            return _append_error(state, "Missing identity for post.")

        decision = _apply_post_promotion_defaults(
            state.main_decision or XPipelineDecision(decision="post"),
            state,
        )
        try:
            draft = await self.post_agent.draft(
                state.identity,
                promote=True,
                promote_target=decision.promote_target,
                specialist_instructions=decision.specialist_instructions,
            )
        except Exception as exc:
            return _append_error(state, f"Post draft failed: {exc}")

        return replace(state, pending_draft=draft, main_decision=decision)

    async def apply_action(self, state: XGraphState) -> XGraphState:
        draft = state.pending_draft
        if draft is None or state.identity is None:
            return state

        result: dict[str, Any] = {"dry_run": not state.live}
        replies_this_run = state.replies_this_run
        posts_this_run = state.posts_this_run

        if draft.kind == "reply" and state.selected_target is not None:
            if state.live:
                try:
                    result = self.x_client.reply(state.selected_target.tweet_id, draft.body)
                except Exception as exc:
                    self.quota_store.set_cooldown(
                        state.identity.id,
                        float(QUOTA_CONFIG["RATE_LIMIT_COOLDOWN_HOURS"]),
                    )
                    return _append_error(state, f"Reply submit failed: {exc}")
            self.quota_store.record_reply(state.identity.id)
            replies_this_run += 1
        elif draft.kind == "post":
            if state.live:
                try:
                    result = self.x_client.post(draft.body)
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

        if draft.kind == "reply":
            return replace(
                state,
                pending_draft=None,
                replies_this_run=replies_this_run,
                action_log=log,
            )
        return replace(
            state,
            pending_draft=None,
            posts_this_run=posts_this_run,
            action_log=log,
        )


def build_x_shill_graph(workflow: XShillWorkflow):
    if StateGraph is None:
        raise XGraphError("langgraph is required to build the X shill graph.")

    graph = StateGraph(XGraphState)
    graph.add_node("main_think", workflow.main_think)
    graph.add_node("browse", workflow.browse)
    graph.add_node("wait_after_browse", workflow.wait_after_browse)
    graph.add_node("wait_before_apply", workflow.wait_before_apply)
    graph.add_node("skip_flip", workflow.skip_flip)
    graph.add_node("pick_target", workflow.pick_target)
    graph.add_node("generate_reply", workflow.generate_reply)
    graph.add_node("generate_post", workflow.generate_post)
    graph.add_node("apply_action", workflow.apply_action)

    graph.set_entry_point("main_think")
    graph.add_conditional_edges(
        "main_think",
        _route_from_think,
        {
            "browse": "browse",
            "browse_seeds": "browse",
            "reply": "pick_target",
            "post": "generate_post",
            "skip": END,
            "done": END,
        },
    )
    graph.add_edge("browse", "wait_after_browse")
    graph.add_edge("wait_after_browse", "skip_flip")
    graph.add_conditional_edges(
        "skip_flip",
        _route_after_skip,
        {
            "done": END,
            "continue": "main_think",
        },
    )
    graph.add_edge("pick_target", "generate_reply")
    graph.add_edge("generate_reply", "wait_before_apply")
    graph.add_edge("generate_post", "wait_before_apply")
    graph.add_edge("wait_before_apply", "apply_action")
    graph.add_edge("apply_action", "main_think")

    return graph.compile()


def initial_state(**kwargs) -> XGraphState:
    return XGraphState(**kwargs)


def _route_from_think(state: XGraphState) -> str:
    decision = state.main_decision.decision if state.main_decision else "done"
    if decision in {"reply", "post"} and not state.browse_satisfied:
        return "browse"
    if decision == "reply" and state.replies_this_run >= QUOTA_CONFIG["MAX_REPLIES_PER_RUN"]:
        return "done"
    if decision == "post" and state.posts_this_run >= QUOTA_CONFIG["MAX_POSTS_PER_RUN"]:
        return "done"
    return decision


def _route_after_skip(state: XGraphState) -> str:
    if state.main_decision and state.main_decision.decision == "done":
        return "done"
    if state.skip_after_browse:
        return "done"
    return "continue"


def _rounds_exhausted(state: XGraphState, config: dict[str, Any]) -> bool:
    return state.main_round >= int(config["MAIN_AGENT_MAX_ROUNDS"])


def _with_decision(state: XGraphState, decision: XPipelineDecision) -> XGraphState:
    return replace(state, main_decision=decision)


def _done_decision(reason: str) -> XPipelineDecision:
    return XPipelineDecision(decision="done", reason=reason)


def _append_error(state: XGraphState, message: str) -> XGraphState:
    return replace(state, errors=[*state.errors, message])


def _enforce_invariants(
    decision: XPipelineDecision,
    state: XGraphState,
    quota_store: QuotaStore,
) -> XPipelineDecision:
    identity_id = state.identity.id if state.identity else ""

    if decision.decision == "post":
        ok, reason = quota_store.can_post(identity_id)
        if not ok:
            logger.info("Post decision overridden (%s); preferring reply or done.", reason)
            ok_reply, _ = quota_store.can_reply(identity_id)
            if ok_reply and state.browse_satisfied:
                return replace(
                    decision,
                    decision="reply",
                    promote=True,
                    reason=f"Post blocked by quota ({reason}); falling back to reply.",
                )
            return _done_decision(f"Post blocked: {reason}")

        if not should_allow_post():
            logger.info("Post decision overridden by P_ALLOW_POST ratio gate; preferring reply.")
            ok_reply, _ = quota_store.can_reply(identity_id)
            if (
                ok_reply
                and state.browse_satisfied
                and state.replies_this_run < QUOTA_CONFIG["MAX_REPLIES_PER_RUN"]
            ):
                return replace(
                    decision,
                    decision="reply",
                    promote=True,
                    promote_target=resolve_promote_target(
                        state.identity,
                        promote=True,
                        decision_target=decision.promote_target,
                    ),
                    reason="Post ratio gate → reply (replies favored over posts).",
                )
            return _done_decision("Post ratio gate; no reply slot available.")

        return _apply_post_promotion_defaults(decision, state)

    if decision.decision == "reply":
        ok, reason = quota_store.can_reply(identity_id)
        if not ok:
            return _done_decision(f"Reply blocked: {reason}")

    if decision.decision in {"reply", "post"} and not state.browse_satisfied:
        return replace(decision, decision="browse", reason="Must browse before writing.")

    return decision


def _apply_post_promotion_defaults(
    decision: XPipelineDecision,
    state: XGraphState,
) -> XPipelineDecision:
    """Posts always promote; promote_target uses same rule as replies."""
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


def _pick_search_query(state: XGraphState, requested: str) -> str:
    if requested.strip():
        return requested.strip()

    identity = state.identity
    if identity is None:
        return random.choice(X_CONFIG["DEFAULT_SEARCH_QUERIES"])

    queries = list(identity.search_queries) or list(X_CONFIG["DEFAULT_SEARCH_QUERIES"])
    # Optionally blend a hashtag into the search string
    if identity.hashtags and random.random() < 0.4:
        tag = random.choice(identity.hashtags).lstrip("#")
        base = random.choice(queries)
        return f"({base}) OR #{tag} -is:retweet lang:en"
    recent = set(state.quota_snapshot.get("identity", {}).get("last_queries", []))
    candidates = [q for q in queries if q not in recent] or queries
    chosen = random.choice(candidates)
    return f"{chosen} -is:retweet lang:en"


def _write_artifact(state: XGraphState, draft, result: dict[str, Any]) -> Path:
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


# Back-compat aliases
RedditGraphError = XGraphError
RedditShillWorkflow = XShillWorkflow
build_reddit_shill_graph = build_x_shill_graph
