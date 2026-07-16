# Entourage Reddit Shiller

CLI-first LangGraph swarm for natural Reddit engagement with multiple personas promoting Entourage app/blog **subtly**.

## Quick start

```bash
cd agents_army_reddit_shiller
python -m venv .deployment_env
source .deployment_env/Scripts/activate   # Git Bash on Windows
pip install -r requirements.txt
cp config.example.env .env                # fill keys + OAuth per identity
```

Dry-run smoke (no API keys):

```bash
python -m reddit_manager.workers.run_shill_job --identity maya_habits --mock-llm --fast --force
```

Dry-run with real LLM (still no Reddit writes):

```bash
python -m reddit_manager.workers.run_shill_job --identity maya_habits --fast --force
```

Live submit (requires OAuth env vars for identity):

```bash
python -m reddit_manager.workers.run_shill_job --identity maya_habits --live
```

## Architecture

- One run = one identity from `reddit_manager/identities/*.yaml` (14 active: 8 app users + 6 blog readers; 2 deactivated for planned Inspiration Tab)
- `RedditPipelineAgent` (supervisor) routes browse/comment/post/skip/done
- `CommentAgent` / `PostAgent` are thin text drafters
- Humanization gates: browse-before-write, jitter waits, skip coin flip, `genuine_reply` gate (~25%) dials off supervisor promote, specialist softens promo tone
- Artifacts under `artifacts/<run_id>/`; quota state under `state/quota_state.json`

See [PIPELINE.md](PIPELINE.md), [docs/IP_ROTATION.md](docs/IP_ROTATION.md), and [docs/REDDIT_ACCOUNTS_PLAYBOOK.md](docs/REDDIT_ACCOUNTS_PLAYBOOK.md) (one account + one OAuth app per identity).

## Account warmup (ops)

Use aged accounts with organic history before enabling `--live`. Start with low volume, mostly genuine (no-promo) comments, and long irregular gaps between runs.
