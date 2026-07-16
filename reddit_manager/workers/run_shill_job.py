"""CLI entrypoint for one Reddit shill run."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import uuid
from dataclasses import asdict
from pathlib import Path

from reddit_manager.agents import CommentAgent, PostAgent, RedditPipelineAgent
from reddit_manager.config import SERVER_CONFIG, WORKER_CONFIG
from reddit_manager.graphs import RedditShillWorkflow, build_reddit_shill_graph, initial_state
from reddit_manager.services.humanization import should_skip_after_browse
from reddit_manager.services.identity_loader import pick_identity, resolve_credentials
from reddit_manager.services.llm_client import RedditLlmClient
from reddit_manager.services.praw_client import RedditClient
from reddit_manager.services.quota_store import QuotaStore
from reddit_manager.services.scheduler import compute_next_eligible_at

logger = logging.getLogger(__name__)


async def run_shill_job(
    *,
    identity_id: str | None = None,
    live: bool = False,
    dry_run: bool | None = None,
    fast: bool = False,
    force: bool = False,
    mock_llm: bool = False,
) -> dict:
    resolved_dry_run = bool(WORKER_CONFIG["DRY_RUN"] if dry_run is None else dry_run)
    if live:
        resolved_dry_run = False

    identity = pick_identity(identity_id, require_credentials=live)
    quota_store = QuotaStore()
    allowed, reason = quota_store.can_start_run(identity.id, force=force and not live)
    if not allowed:
        logger.info("Run blocked: %s", reason)
        return {"ok": True, "status": "blocked", "reason": reason, "identity": identity.id}

    credentials = resolve_credentials(identity)
    reddit_client = RedditClient(credentials=credentials, live=live and not resolved_dry_run)
    reddit_client.login()

    run_id = uuid.uuid4().hex[:12]
    artifacts_dir = str(Path(WORKER_CONFIG["ARTIFACTS_ROOT"]) / run_id)
    Path(artifacts_dir).mkdir(parents=True, exist_ok=True)

    workflow = RedditShillWorkflow(
        reddit_client=reddit_client,
        quota_store=quota_store,
        pipeline_agent=_build_pipeline_agent(mock_llm),
        comment_agent=_build_comment_agent(mock_llm),
        post_agent=_build_post_agent(mock_llm),
    )
    graph = build_reddit_shill_graph(workflow)

    state = initial_state(
        identity=identity,
        live=live and not resolved_dry_run,
        fast=fast or resolved_dry_run,
        run_id=run_id,
        artifacts_dir=artifacts_dir,
        skip_after_browse=should_skip_after_browse(),
        quota_snapshot=quota_store.get_snapshot(identity.id),
    )

    quota_store.record_run_start(identity.id)
    final_state = await graph.ainvoke(state)
    quota_store.set_next_eligible_at(identity.id, compute_next_eligible_at())

    errors = _state_get(final_state, "errors", [])
    action_log = _state_get(final_state, "action_log", [])

    summary = {
        "ok": not errors,
        "identity": identity.id,
        "run_id": run_id,
        "dry_run": resolved_dry_run,
        "live": live and not resolved_dry_run,
        "mock_llm": mock_llm,
        "decisions": [
            _serialize_log_entry(entry)
            for entry in action_log
            if _log_action(entry) in {"browse", "apply", "skip_forced", "target_picked"}
        ],
        "errors": errors,
        "artifacts_dir": artifacts_dir,
    }
    _write_summary(artifacts_dir, summary)
    return summary


def _write_summary(artifacts_dir: str, summary: dict) -> None:
    path = Path(artifacts_dir) / "summary.json"
    path.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")


def _configure_logging() -> None:
    logging.basicConfig(
        level=getattr(logging, SERVER_CONFIG["LOG_LEVEL"].upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Run one Reddit shill job for a single identity.")
    parser.add_argument("--identity", help="Identity id (YAML filename stem). Random if omitted.")
    parser.add_argument("--live", action="store_true", help="Submit to Reddit (requires OAuth env vars).")
    parser.add_argument("--dry-run", action="store_true", help="Force dry-run even if REDDIT_DRY_RUN=false.")
    parser.add_argument("--fast", action="store_true", help="Use shortened human waits (for testing).")
    parser.add_argument("--force", action="store_true", help="Bypass scheduler spacing (not allowed with --live).")
    parser.add_argument("--mock-llm", action="store_true", help="Use deterministic mock LLM responses (smoke tests).")
    args = parser.parse_args()

    if args.live and args.force:
        parser.error("--force cannot be used with --live.")

    _configure_logging()
    summary = asyncio.run(
        run_shill_job(
            identity_id=args.identity,
            live=args.live,
            dry_run=True if args.dry_run else None,
            fast=args.fast,
            force=args.force,
            mock_llm=args.mock_llm,
        )
    )
    print(json.dumps(summary, indent=2, default=str))


class _MockLlmClient(RedditLlmClient):
    def __init__(self, responder):
        super().__init__()
        self._responder = responder

    async def chat_completion(self, messages: list[dict[str, str]]) -> str:
        return self._responder(messages)


def _build_pipeline_agent(mock_llm: bool) -> RedditPipelineAgent:
    if not mock_llm:
        return RedditPipelineAgent()

    def responder(messages: list[dict[str, str]]) -> str:
        payload = json.loads(messages[-1]["content"])
        if not payload.get("browse_satisfied"):
            return (
                '{"decision":"browse","reason":"Need context","subreddit":"getdisciplined",'
                '"sort":"hot","promote":false,"promote_target":"none","specialist_instructions":""}'
            )
        if int(payload.get("comments_this_run", 0)) >= 1:
            return '{"decision":"done","reason":"Finished","promote":false,"promote_target":"none","specialist_instructions":""}'
        return (
            '{"decision":"comment","reason":"Helpful reply with soft promo","subreddit":"getdisciplined",'
            '"sort":"hot","promote":true,"promote_target":"app","specialist_instructions":"Be supportive first."}'
        )

    return RedditPipelineAgent(llm_client=_MockLlmClient(responder))


def _build_comment_agent(mock_llm: bool) -> CommentAgent:
    if not mock_llm:
        return CommentAgent()

    def responder(messages: list[dict[str, str]]) -> str:
        return '{"body":"I have been there too — tiny steps and forgiving streaks helped me more than all-or-nothing plans."}'

    return CommentAgent(llm_client=_MockLlmClient(responder))


def _build_post_agent(mock_llm: bool) -> PostAgent:
    if not mock_llm:
        return PostAgent()

    def responder(messages: list[dict[str, str]]) -> str:
        return '{"title":"What actually helped me restart after falling off","body":"Sharing in case it helps someone else."}'

    return PostAgent(llm_client=_MockLlmClient(responder))


def _state_get(state, key: str, default):
    if isinstance(state, dict):
        return state.get(key, default)
    return getattr(state, key, default)


def _log_action(entry) -> str:
    if isinstance(entry, dict):
        return entry.get("action", "")
    return getattr(entry, "action", "")


def _serialize_log_entry(entry) -> dict:
    if isinstance(entry, dict):
        return entry
    return asdict(entry)


if __name__ == "__main__":
    main()
