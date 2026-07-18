# Identity activation

Edit [`x_manager/identities/activation.yaml`](../x_manager/identities/activation.yaml) to enable personas.

## Current starter set (live-ready when credentials exist)

| Id | Type | Why first |
|----|------|-----------|
| `maya_habits` | app_user | Core habit / formation story |
| `jordan_stoic` | app_user | Core mood / journaling story |
| `riley_blog` | blog_reader | Habits / Productivity / Inner Work blog |

## How to activate the next identity

1. Create unique X account + OAuth 1.0a tokens (see [X_ACCOUNTS_PLAYBOOK.md](X_ACCOUNTS_PLAYBOOK.md)).
2. Fill `X_{ENV_PREFIX}_*` in `.env` (API key/secret, access token/secret, optional proxy).
3. In `activation.yaml`: move the id from `deactivated.*` into `active.app_users` or `active.blog_readers`.
4. Optionally set `active: true` in that persona’s YAML for documentation (loader uses `activation.yaml` as source of truth).
5. Dry-run: `python -m x_manager.workers.run_shill_job --identity <id> --mock-llm --fast --force`

## Rules

- Only identities listed under `active` are returned by `list_identities()` / random pick.
- `get_identity(id)` fails if the id is deactivated.
- Do not activate all remaining personas at once — one account at a time.
- Persona browse targets live in YAML as `search_queries`, `hashtags`, and optional `seed_accounts`.
