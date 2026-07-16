from reddit_manager.services.identity_loader import get_identity, list_all_identities, list_identities, pick_identity, resolve_credentials
from reddit_manager.services.quota_store import QuotaStore
import pytest


def test_list_identities_has_fourteen_active_personas() -> None:
    identities = list_identities()
    assert len(identities) == 14
    ids = {identity.id for identity in identities}
    assert "maya_habits" in ids
    assert "morgan_blog" in ids
    assert "casey_relationships" in ids
    assert "avery_love" in ids
    assert "devon_purpose" in ids
    assert "harper_philosophy" in ids
    assert "nova_inspiration" not in ids
    assert "elliot_reflection" not in ids
    assert sum(1 for i in identities if i.type == "blog_reader") == 6


def test_list_all_identities_includes_deactivated() -> None:
    identities = list_all_identities()
    assert len(identities) == 16
    assert {i.id for i in identities if not i.active} == {"nova_inspiration", "elliot_reflection"}


def test_deactivated_identity_cannot_be_loaded() -> None:
    with pytest.raises(Exception, match="deactivated"):
        get_identity("nova_inspiration")


def test_resolve_promote_target_uses_identity_bias() -> None:
    from reddit_manager.agents.reddit_pipeline_agent import resolve_promote_target
    from reddit_manager.schemas import IdentityCard

    blog_reader = IdentityCard(
        id="riley_blog",
        display_name="Riley",
        type="blog_reader",
        background="",
        usage_or_reading_pattern="",
        core_purpose_or_topics="",
        favorite_features_or_angles="",
        voice="",
        preferred_subreddits=[],
        promo_bias="blog",
        env_prefix="RILEY",
        system_prompt="",
    )
    assert resolve_promote_target(blog_reader, promote=True, decision_target="none") == "blog"
    assert resolve_promote_target(blog_reader, promote=True, decision_target="app") == "app"


def test_post_promotion_defaults_for_app_user() -> None:
    from reddit_manager.agents.reddit_pipeline_agent import parse_pipeline_decision
    from reddit_manager.schemas import IdentityCard, RedditGraphState

    state = RedditGraphState(
        identity=IdentityCard(
            id="maya_habits",
            display_name="Maya",
            type="app_user",
            background="",
            usage_or_reading_pattern="",
            core_purpose_or_topics="",
            favorite_features_or_angles="",
            voice="",
            preferred_subreddits=[],
            promo_bias="app",
            env_prefix="MAYA",
            system_prompt="",
        )
    )
    decision = parse_pipeline_decision('{"decision":"post","reason":"test"}', state)
    assert decision.promote is True
    assert decision.promote_target == "app"


def test_genuine_reply_gate_is_comment_only_path() -> None:
    """pick_target sets genuine_reply; generate_post forces promote regardless."""
    from reddit_manager.graphs.reddit_shill_graph import _apply_post_promotion_defaults
    from reddit_manager.schemas import IdentityCard, RedditGraphState, RedditPipelineDecision

    state = RedditGraphState(
        identity=IdentityCard(
            id="maya_habits",
            display_name="Maya",
            type="app_user",
            background="",
            usage_or_reading_pattern="",
            core_purpose_or_topics="",
            favorite_features_or_angles="",
            voice="",
            preferred_subreddits=[],
            promo_bias="app",
            env_prefix="MAYA",
            system_prompt="",
        ),
        genuine_reply=True,
    )
    result = _apply_post_promotion_defaults(RedditPipelineDecision(decision="post"), state)
    assert result.promote is True
    assert result.promote_target == "app"


def test_quota_store_blocks_second_run_same_day() -> None:
    store = QuotaStore(root="artifacts/test_state")
    allowed, _ = store.can_start_run("maya_habits", force=True)
    assert allowed
    store.record_run_start("maya_habits")
    allowed, reason = store.can_start_run("maya_habits")
    assert not allowed
    assert "daily run limit" in reason
