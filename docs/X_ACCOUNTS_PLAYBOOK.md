# X Accounts Playbook

One marketing identity → one X account → one OAuth 1.0a credential set → one sticky proxy.

## Principles

- **Never** share an X account or tokens across identities.
- Prefer aged, organic-looking accounts before `--live`.
- Keep volume low: reply ≫ post; respect quotas and humanization gates.
- X restricts spam and deceptive automation — helpful-first is mandatory, not optional.

## Per-identity checklist

1. Create / warm an X account aligned with the persona (bio, avatar, light organic activity).
2. Create a developer app (or use per-account tokens) with **tweet read/write** permissions.
3. Generate **OAuth 1.0a** user tokens:
   - API key + API secret (consumer)
   - Access token + access token secret
4. Put secrets in `.env` only (never in YAML):

```env
X_MAYA_HABITS_API_KEY=
X_MAYA_HABITS_API_SECRET=
X_MAYA_HABITS_ACCESS_TOKEN=
X_MAYA_HABITS_ACCESS_TOKEN_SECRET=
X_MAYA_HABITS_USERNAME=
X_MAYA_HABITS_HTTP_PROXY=
X_MAYA_HABITS_USER_AGENT=
```

5. Assign a sticky residential proxy (see [IP_ROTATION.md](IP_ROTATION.md)).
6. Activate the identity in [`activation.yaml`](../x_manager/identities/activation.yaml).
7. Dry-run: `python -m x_manager.workers.run_shill_job --identity maya_habits --mock-llm --fast --force`
8. Optional real-LLM dry-run, then `--live` only when ready.

## Isolation

| Resource | Rule |
|----------|------|
| X account | 1 per identity |
| OAuth tokens | 1 set per identity |
| Sticky proxy | 1 session per identity |
| Host runs | 1 identity active at a time |

## Warmup before live

- Post a few organic tweets / replies manually over days.
- Grow a tiny follower set naturally; avoid bot farms.
- Start live with `genuine_reply`-heavy behavior (runtime already biases helpful replies).

## Out of scope (v1)

- Quote tweets, DMs, likes/follows automation
- Unofficial clients / browser automation
- Shared app keys across many personas (allowed for early testing only; prefer per-identity)

## Related

- [IDENTITY_ACTIVATION.md](IDENTITY_ACTIVATION.md)
- [IP_ROTATION.md](IP_ROTATION.md)
- [../PIPELINE.md](../PIPELINE.md)
