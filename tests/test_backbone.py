from x_manager.services.identity_loader import (
    clear_activation_cache,
    get_identity,
    list_all_identities,
    list_identities,
)
from x_manager.services.quota_store import QuotaStore
import pytest


@pytest.fixture(autouse=True)
def _clear_roster_cache():
    clear_activation_cache()
    yield
    clear_activation_cache()


def test_list_identities_starter_set_only() -> None:
    identities = list_identities()
    assert len(identities) == 3
    ids = {identity.id for identity in identities}
    assert ids == {"maya_habits", "jordan_stoic", "riley_blog"}
    assert sum(1 for i in identities if i.type == "app_user") == 2
    assert sum(1 for i in identities if i.type == "blog_reader") == 1
    maya = next(i for i in identities if i.id == "maya_habits")
    assert maya.search_queries
    assert maya.hashtags


def test_list_all_identities_includes_deactivated() -> None:
    identities = list_all_identities()
    assert len(identities) == 16
    active = {i.id for i in identities if i.active}
    deactivated = {i.id for i in identities if not i.active}
    assert active == {"maya_habits", "jordan_stoic", "riley_blog"}
    assert "nova_inspiration" in deactivated
    assert "morgan_blog" in deactivated
    assert len(deactivated) == 13


def test_deactivated_identity_cannot_be_loaded() -> None:
    with pytest.raises(Exception, match="deactivated"):
        get_identity("morgan_blog")
    with pytest.raises(Exception, match="deactivated"):
        get_identity("nova_inspiration")


def test_resolve_promote_target_uses_identity_bias() -> None:
    from x_manager.agents.x_pipeline_agent import resolve_promote_target
    from x_manager.schemas import IdentityCard

    blog_reader = IdentityCard(
        id="riley_blog",
        display_name="Riley",
        type="blog_reader",
        background="",
        usage_or_reading_pattern="",
        core_purpose_or_topics="",
        favorite_features_or_angles="",
        voice="",
        search_queries=[],
        hashtags=[],
        seed_accounts=[],
        promo_bias="blog",
        env_prefix="RILEY",
        system_prompt="",
    )
    assert resolve_promote_target(blog_reader, promote=True, decision_target="none") == "blog"
    assert resolve_promote_target(blog_reader, promote=True, decision_target="app") == "app"


def test_post_promotion_defaults_for_app_user() -> None:
    from x_manager.agents.x_pipeline_agent import parse_pipeline_decision
    from x_manager.schemas import IdentityCard, XGraphState

    state = XGraphState(
        identity=IdentityCard(
            id="maya_habits",
            display_name="Maya",
            type="app_user",
            background="",
            usage_or_reading_pattern="",
            core_purpose_or_topics="",
            favorite_features_or_angles="",
            voice="",
            search_queries=[],
            hashtags=[],
            seed_accounts=[],
            promo_bias="app",
            env_prefix="MAYA",
            system_prompt="",
        )
    )
    decision = parse_pipeline_decision('{"decision":"post","reason":"test"}', state)
    assert decision.promote is True
    assert decision.promote_target == "app"


def test_legacy_comment_decision_maps_to_reply() -> None:
    from x_manager.agents.x_pipeline_agent import parse_pipeline_decision

    decision = parse_pipeline_decision('{"decision":"comment","reason":"legacy"}')
    assert decision.decision == "reply"


def test_genuine_reply_gate_is_reply_only_path() -> None:
    """pick_target sets genuine_reply; generate_post forces promote regardless."""
    from x_manager.graphs.x_shill_graph import _apply_post_promotion_defaults
    from x_manager.schemas import IdentityCard, XGraphState, XPipelineDecision

    state = XGraphState(
        identity=IdentityCard(
            id="maya_habits",
            display_name="Maya",
            type="app_user",
            background="",
            usage_or_reading_pattern="",
            core_purpose_or_topics="",
            favorite_features_or_angles="",
            voice="",
            search_queries=[],
            hashtags=[],
            seed_accounts=[],
            promo_bias="app",
            env_prefix="MAYA",
            system_prompt="",
        ),
        genuine_reply=True,
    )
    result = _apply_post_promotion_defaults(XPipelineDecision(decision="post"), state)
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


def test_x_client_fixture_search() -> None:
    from x_manager.services.x_client import XClient

    client = XClient(credentials=None, live=False)
    client.login()
    items = client.search_recent("habit building", max_results=10)
    assert items
    assert items[0].tweet_id
    assert items[0].text
