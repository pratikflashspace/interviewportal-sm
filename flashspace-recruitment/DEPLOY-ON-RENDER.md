# Deploy the complete Flashspace project

Follow README.md for the fresh GitHub upload, then continue here. Never commit credentials.

## 2. Create an external PostgreSQL database

1. Create/sign in to a Neon account at https://neon.com/ and create a project on its Free plan. Another managed PostgreSQL provider also works if its limits and connection settings are appropriate.
2. Create/select a dedicated new database for this pilot. Do not use an unrelated production database.
3. Copy its PostgreSQL connection string from **Connect**. Keep `sslmode=require` or stronger. The hostname should be near your Render region where practical. The URL is a secret because it contains the database password.
4. You will paste that string into Render as `DATABASE_URL`. Do not send it in chat or commit it to GitHub.

The application creates its own tables on first startup. This is a **fresh database setup**, not an automatic migration of an old Render SQLite database. If you already collected real candidates with the old version, stop and plan a data migration before switching. The app refuses to fall back to local SQLite on Render.

Neon Free has storage/compute quotas. Free storage is not unlimited and is not a backup policy. Review provider terms and establish exports/backups. Render's free Postgres offering is time-limited, so do not select it assuming permanent free persistence.

## 3. Configure the Render screen you are on

You selected a **Web Service**, which is correct. This is not a Static Site.

```text
Language:       Python 3
Branch:         main (or your actual uploaded branch)
Region:         Singapore (or your chosen region)
Root Directory: leave blank if backend/ and requirements.txt are at repository root
Instance Type:  Free
```

Build command:

```bash
pip install -r requirements.txt && python -m unittest discover -s tests
```

Start command:

```bash
gunicorn 'backend.server:create_app()' --bind 0.0.0.0:$PORT --workers 1 --threads 8 --timeout 120 --access-logfile /dev/null
```

Health check path:

```text
/api/health
```

Do not add a persistent disk. Do not set the root to `web`, `cloudflare`, or `backend`. Keep one Gunicorn worker and one Render instance for this pilot. If your repository contains an outer enclosing folder, set the root to that exact folder instead; the root must contain `backend/`, `web/`, `roles.json` and `requirements.txt` together.

The included `render.yaml` carries equivalent settings for Blueprint deployment. **Editing render.yaml does not configure an independently created manual Web Service.** On your current manual screen, enter the commands and environment values yourself.

## 4. Set Render environment variables

Set these only under Render's service Environment settings (or its initial deployment form):

| Variable | Value |
| --- | --- |
| `DATABASE_URL` | Secret PostgreSQL connection string from Neon, including TLS settings |
| `REQUIRE_DATABASE_URL` | `true` |
| `CLOUDFLARE_ACCOUNT_ID` | The 32-character Account ID supplied by the Cloudflare account owner |
| `CLOUDFLARE_GATEWAY_ID` | Your Gateway ID, e.g. the gateway name you were given |
| `CLOUDFLARE_API_TOKEN` | **Rotated/replacement** Cloudflare API token with Workers AI inference permission |
| `CLOUDFLARE_LLM_MODEL` | `@cf/meta/llama-3.1-8b-instruct-fast` |
| `CLOUDFLARE_TTS_SPEAKER` | `luna` |
| `CLICKUP_API_TOKEN` | Your ClickUp API token for the private hiring Folder |
| `CLICKUP_FOLDER_ID` | Numeric hiring Folder ID, not a List ID |
| `ADMIN_EMAIL` | A recruiter email distinct from candidate test accounts |
| `ADMIN_PASSWORD` | Unique password, 16 to 128 characters |
| `MAX_AI_CALLS_PER_DAY` | `100` for initial testing |
| `PYTHON_VERSION` | `3.12.10` |

Do not set `DATABASE_PATH`, `OPENAI_API_KEY`, `OPENAI_MODEL`, `OPENAI_STT_MODEL`, `OPENAI_TTS_MODEL`, `ADMIN_PASSWORD_KEY` or `AUTH_PEPPER` for this version. They belong to older versions and are not needed here. The original login form remains password-based; the backend uses salted scrypt.

For the normal Render URL, **omit `APP_ORIGIN`**. Render's `RENDER_EXTERNAL_URL` is used automatically. If you add a custom domain later, set `APP_ORIGIN` to the exact public HTTPS origin with no trailing slash, and use that domain for login/forms. Do not set localhost as APP_ORIGIN on Render.

Your account owner does not need to grant you permission to deploy Cloudflare Workers or manage D1 for this architecture. They must supply a replacement API token that can run the selected models and route through the existing gateway. That permission is distinct from gateway configuration/admin access. Their quota, billing and data-handling settings still apply.

## 5. Deploy and test

1. Save the environment variables and deploy the latest GitHub commit. Wait for the service to become live.
2. Open its Render URL. If no jobs appear, edit the **root** `roles.json` and set approved actual roles to `published: true`, then commit/redeploy. The supplied sample jobs are unpublished; replace them with your real vacancies.
3. Register two fictional candidate accounts, and confirm each only sees its own applications and cannot open recruiter reports.
4. Apply to a role. Record an English answer, stop recording and inspect the transcript. Test microphone-denied and typed-answer paths too. Cloudflare model/audio-container availability needs checking in real browsers.
5. Submit all four answers. As a recruiter, log in using `ADMIN_EMAIL` and the original `ADMIN_PASSWORD`; refresh the application view while reports and sync process.
6. Verify the corresponding List/task in your private ClickUp Folder, including profile, consent, transcript, summary, provisional score and exact quote evidence.
7. Restart or redeploy Render, then log back in and verify that accounts, answers and remote task IDs persist in PostgreSQL.
8. Before inviting real candidates, replace the pilot privacy notice with your actual privacy contact/retention terms, establish coordinated deletion/backup procedures and validate each role's scoring rubric with a human.

### Free hosting is not continuous background processing

Render Free can sleep after inactivity and takes time to wake. The app avoids keeping Neon awake indefinitely: after 10 minutes without non-health-check HTTP requests, its local background polling pauses. **Pending interviews/reports/sync jobs stay in Postgres and resume when a visitor opens the website again.** Keep the recruiter page active and use Refresh while testing. Immediate reports are not guaranteed on free infrastructure.

The health endpoint confirms that the app process is running; it intentionally does not query Neon on every Render health probe. Test login/applications to verify database connectivity.

AI inference can cost money. The 100-call cap is an application request counter, not an exact currency or neuron budget. Set account-level budgets with the Cloudflare owner. There is no automatic paid-model fallback. The old per-interview cost estimate was not verified and is not a guarantee.

## Credentials, gateway routing and API correctness

The Python backend uses Cloudflare's documented model-in-path REST endpoint:

```text
https://api.cloudflare.com/client/v4/accounts/{ACCOUNT_ID}/ai/run/{MODEL_ID}
```

It sends `Authorization: Bearer <replacement token>` and `cf-aig-gateway-id: <gateway ID>`. It requests cache bypass and disables gateway content logging per request using `cf-aig-skip-cache: true` and `cf-aig-collect-log: false`. The owner must verify the effective gateway/provider retention policy; those headers are not a blanket zero-retention guarantee.

It does **not** blindly copy the earlier `/audio/transcriptions` or `/audio/generations` URLs from the pasted chat. STT sends base64-encoded recorded audio to Whisper; TTS sends `text`, `speaker` and `encoding: mp3` to Aura-2. Flux streaming is not implemented by this patch. STT → LLM → TTS remains a real voice-interview pipeline, but with explicit candidate-controlled turns.

Model JSON is validated before saving questions/scores. Invented evidence quotes reject a report. Scores are advisory and are not an automatic hire/reject/ranking decision. Claim verification and hiring fairness still need human evaluation.

## Maintenance and limitations

This package uses Render Free and external PostgreSQL. No paid disk or OpenAI-hosted API is configured.

Render Free does not provide a service shell. For an authorized password reset, a developer can run `python manage.py reset-password <exact-email>` locally with Python dependencies and the same secure DATABASE_URL. Verify the person's identity first. Changing ADMIN_PASSWORD in Render does not reset an existing stored admin password. The script refuses to run SQLite backups against Postgres; use database-native backup tools/provider facilities, with protected credentials.

The new database tables are created idempotently at runtime, but there is no general schema migration engine or import of old SQLite users. Run one web worker/instance. The background sync uses a Postgres advisory transaction lock to reduce overlap across restarts/deploys. Existing ClickUp sync uses stable-reference reconciliation; ambiguous API timeouts/eventual consistency can still require manual duplicate reconciliation, as in the original MVP.

No email verification, self-service account recovery, automatic retention/deletion, binary resume upload, continuous audio streaming, or enterprise compliance certification was added. Test account/model access and document privacy terms before public use.

## Checks completed before packaging

- **46 tests passed**, including the original 25 backend tests and 21 new Cloudflare/Postgres-configuration tests.
- One optional **real PostgreSQL integration test was skipped**, because no disposable database or psycopg installation was available in the sandbox. It can be run by setting `TEST_POSTGRES_URL` to a dedicated test database on a developer machine; it creates and drops only its own unique test schema. Do not set that variable to production in Render.
- Tests were rerun with Render-like environment variables to ensure temporary test databases do not touch a configured production DATABASE_URL.
- Frontend rebuilt successfully; consent/provider disclosures were checked on desktop and mobile.
- Provider requests use mocked responses in tests. No Cloudflare token was used and no live AI, ClickUp, Neon or Render account was contacted.

**This package is prepared and locally tested, not deployed or production-certified.** The sandbox has no internet access. Verify actual PostgreSQL driver/connectivity, Cloudflare permission/model response formats, voice quality and provider quotas on your test deployment.

Reference documentation:

- https://developers.cloudflare.com/ai-gateway/usage/rest-api/
- https://developers.cloudflare.com/ai-gateway/usage/providers/workersai/
- https://developers.cloudflare.com/workers-ai/models/whisper-large-v3-turbo/
- https://developers.cloudflare.com/workers-ai/models/aura-2-en/
- https://render.com/docs/free
- https://neon.com/pricing
