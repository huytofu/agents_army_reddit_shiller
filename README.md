# Entourage X Shiller

CLI-first LangGraph swarm for natural **X** engagement with multiple personas promoting Entourage app/blog **subtly**.

> Repo folder remains `agents_army_reddit_shiller`; package is `x_manager`.

## Quick start

```bash
cd agents_army_reddit_shiller
python -m venv .deployment_env
source .deployment_env/Scripts/activate   # Git Bash on Windows
pip install -r requirements.txt
cp config.example.env .env                # fill keys + OAuth per identity
```

Dry-run smoke (no API keys; fixture tweets):

```bash
python -m x_manager.workers.run_shill_job --identity maya_habits --mock-llm --fast --force
```

Dry-run with real LLM (still no X writes):

```bash
python -m x_manager.workers.run_shill_job --identity maya_habits --fast --force
```

Live submit (requires OAuth env vars for identity):

```bash
python -m x_manager.workers.run_shill_job --identity maya_habits --live
```

## Architecture

- One run = one identity from active roster in [`identities/activation.yaml`](x_manager/identities/activation.yaml) (starter: 2 app + 1 blog). See [docs/IDENTITY_ACTIVATION.md](docs/IDENTITY_ACTIVATION.md).
- Browse via **recent search** (+ optional `seed_accounts`); reply ≫ post
- `XPipelineAgent` (supervisor) routes browse/reply/post/skip/done
- `ReplyAgent` / `PostAgent` are thin text drafters
- Humanization gates: browse-before-write, jitter waits, skip coin flip, `genuine_reply` on replies (~25%), specialist softens promo tone
- Artifacts under `artifacts/<run_id>/`; quota state under `state/quota_state.json`
- Platform client: **Tweepy** (X API v2), OAuth 1.0a per identity

See [PIPELINE.md](PIPELINE.md), [docs/IP_ROTATION.md](docs/IP_ROTATION.md), and [docs/X_ACCOUNTS_PLAYBOOK.md](docs/X_ACCOUNTS_PLAYBOOK.md).

## Account warmup (ops)

Use aged accounts with organic history before enabling `--live`. Start with low volume, mostly genuine (no-promo) replies, and long irregular gaps between runs.
